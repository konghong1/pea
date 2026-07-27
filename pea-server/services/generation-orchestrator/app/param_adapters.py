"""模型参数适配器 (Anti-Corruption Layer / Strategy).

为什么存在:
  前端/API 只讲"规范参数"(size_tier, aspect_ratio, n, seed, reference_images),
  不关心具体模型要什么形状。各模型/提供商的请求体差异很大(见官方文档):
    - Agnes 图像: size 用 档位式 "1K"/"2K"/"3K"/"4K" + 可选 ratio;
                  图生图 image 必须放 extra_body.image, 且绝不能发 tags;
                  response_format 必须在 extra_body 内。
    - OpenAI / DALL·E: size 用精确像素 "1024x1024"/"1792x1024", 不认 ratio。
  把这些差异收敛到一个 adapter 层, 后续接入新模型只需新增一个 adapter,
  不污染 provider 主流程, 也不让前端耦合具体模型。

设计:
  - NormImageParams: 规范参数(系统内部通用语)。
  - ImageParamAdapter (ABC) + Agnes / Generic 实现。
  - get_image_adapter(base_url): 按提供商族分派; 默认回退 Generic。
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, unquote

logger = logging.getLogger(__name__)

# 档位式 -> 精确像素 (OpenAI/DALL·E 这类需要精确像素的模型用; DALL·E 非方图最大 1792x1024)
_TIER_TO_PIXELS = {
    "1K": "1024x1024",
    "2K": "1792x1024",
    "3K": "2048x2048",
    "4K": "2048x2048",
}

# Agnes 官方白名单 ratio (其它值丢弃并告警, 避免 400)
_AGNES_RATIOS = {"1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"}


# 匹配内部/不可达 URL 的主机名模式: localhost, 私有 IP, 容器短名, 非标准端口
_INTERNAL_HOST_RE = re.compile(
    r'^(localhost|127\.0\.0\.1|10\.|172\.(1[6-9]|2[0-9]|3[01])\.'
    r'|192\.168\.|::1|::ffff:127\.|minio|bff|mysql|redis|web|nginx)'
    r'|.*:(9000|4000|3306|6379|8088|5174|8000)\b',
    re.IGNORECASE,
)

# BFF 签名 URL 路径中包含的桶名前缀（用于从完整 URL 中提取 object key）
_BUCKET_PATH_PREFIX = '/pea-media/'


def _is_internal_url(url: str) -> bool:
    """判断 URL 是否为外部模型不可达的内部地址。"""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ''
        port = parsed.port
        # 检查主机名
        if _INTERNAL_HOST_RE.match(host):
            return True
        # 检查非标准端口（外部模型通常只允许 80/443）
        if port and port not in (80, 443, 8080, 8443):
            # 公网 CDN 可能用非标准端口，但 localhost/private IP + 非标准端口一定是内部的
            if _INTERNAL_HOST_RE.match(host) or host in ('localhost', '127.0.0.1'):
                return True
    except Exception:
        pass
    return False


def _extract_minio_key_from_url(url: str) -> str | None:
    """从 BFF 签名 URL 中提取 MinIO object key。

    URL 格式: http(s)://{host}:{port}/pea-media/{key}?X-Amz-...
    返回 key 部分（如 u:1/abc123.jpg），不含桶名前缀。
    对 path 做 unquote，避免 key 中的 ':' 等字符被 percent-encoding 后导致 NoSuchKey。
    """
    try:
        parsed = urlparse(url)
        path = parsed.path or ''
        if path.startswith(_BUCKET_PATH_PREFIX):
            return unquote(path[len(_BUCKET_PATH_PREFIX):])
    except Exception:
        pass
    return None


def _resolve_internal_ref_via_minio(url: str) -> str | None:
    """将内部 MinIO 签名 URL 解析为 base64 data: URI。

    流程: 从 URL 提取 object key → 用编排器自有 MinIO 客户端直下 → 转 base64。
    失败返回 None（调用方应丢弃该参考图并告警）。

    鲁棒性: 签名 URL 路径会把 ':' 等字符 percent-encode (u%3A592/...),
    而 MinIO 实际存储的 key 多为字面量 (u:592/...)。故对提取到的 key 同时尝试
    "解码后" 与 "原样" 两种候选, 避免 NoSuchKey 导致参考图被静默丢弃。
    """
    raw_key = _extract_minio_key_from_url(url)
    if not raw_key:
        logger.warning("[refs] internal URL 无法提取 MinIO key: %s", url[:120])
        return None

    decoded = unquote(raw_key)
    candidates = []
    if decoded != raw_key:
        candidates.append(decoded)   # 优先尝试解码后的字面 key (常见情形)
    candidates.append(raw_key)       # 再试原样 (极少数按编码存储的情形)

    try:
        from app.storage import _get_client

        client = _get_client()
        last_exc = None
        for key in candidates:
            try:
                resp = client.get_object('pea-media', key)
                data = resp.read()
                resp.close()
                resp.release_conn()

                # 猜测 MIME 类型
                ct = (
                    getattr(resp, 'content-type', None)
                    or (resp.headers.get('Content-Type') if hasattr(resp, 'headers') else None)
                    or 'image/png'
                )
                mime = ct.split(';')[0].strip() if ct else 'image/png'
                b64 = base64.b64encode(data).decode('ascii')
                result = f'data:{mime};base64,{b64}'
                logger.info(
                    "[refs] 内部参考图已通过 MinIO 直下转为 data: URI (%d bytes, key=%s)",
                    len(data), key[:60],
                )
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("[refs] MinIO 直下尝试 key=%s 失败: %s", key[:60], exc)
        logger.warning("[refs] MinIO 直下所有候选 key 均失败, 最后错误: %s", last_exc)
        return None
    except Exception as exc:
        logger.warning("[refs] MinIO 客户端初始化失败: %s", exc)
        return None


def _normalize_refs(refs: Any) -> list[str]:
    """规范化参考图列表:

    1. 保留公网 http(s) / data: 内联 URI;
    2. 检测到内部 URL（localhost / 私有 IP / 容器名 / 非标准端口）时,
       通过编排器自有 MinIO 客户端下载并转为 base64 data: URI（外部模型可直接消费）；
    3. blob: / 相对路径等不可达地址丢弃。
    上限 8，保序。
    """
    if not refs:
        return []
    if isinstance(refs, str):
        refs = [refs]
    out: list[str] = []
    dropped = 0
    resolved_internal = 0
    for r in list(refs)[:8]:
        if not isinstance(r, str):
            dropped += 1
            continue
        if r.startswith('data:'):
            out.append(r)
        elif r.startswith('http'):
            if _is_internal_url(r):
                converted = _resolve_internal_ref_via_minio(r)
                if converted:
                    out.append(converted)
                    resolved_internal += 1
                else:
                    dropped += 1
            else:
                out.append(r)
        else:
            dropped += 1

    if dropped:
        logger.warning(
            "[refs] dropped %d unreachable reference image(s); %d internal URLs resolved via MinIO",
            dropped, resolved_internal,
        )
    return out


@dataclass
class NormImageParams:
    """规范图像参数 —— 系统内部通用语, 与具体模型无关。"""
    prompt: str
    n: int = 1
    size_tier: str | None = None          # 已大写: "1K"/"2K"/"3K"/"4K"
    aspect_ratio: str | None = None       # "1:1"/"16:9"/...
    seed: int | None = None
    reference_images: list[str] = field(default_factory=list)


def normalize_image_params(req: dict) -> NormImageParams:
    """从 route() 收到的 req 抽取规范参数。前端已带 resolution/aspectRatio, 直接采用。"""
    p = req.get("params") or {}
    tier_raw = (p.get("resolution") or p.get("size") or "")
    tier = tier_raw.upper() if tier_raw else None
    n_raw = p.get("n", 1)
    try:
        n = int(n_raw)
    except (TypeError, ValueError):
        n = 1
    return NormImageParams(
        prompt=req["prompt"],
        n=max(1, min(8, n)),
        size_tier=tier,
        aspect_ratio=p.get("aspectRatio"),
        seed=p.get("seed"),
        reference_images=_normalize_refs(p.get("reference_images")),
    )


class ImageParamAdapter:
    def build(self, norm: NormImageParams, provider) -> dict:
        raise NotImplementedError


class AgnesImageAdapter(ImageParamAdapter):
    """Agnes 2.x 图像: 档位式 size + ratio + extra_body.image, 不发 tags。

    官方文档要点:
      - size 推荐 "1K".."4K" 档位, 配合 ratio 得到可预期尺寸 (2K+16:9 -> 2624x1472)。
      - 图生图 image 放 extra_body.image; 不要传 tags:["img2img"]。
      - response_format 必须在 extra_body 内 (顶层会 400); 但我们直接读 data[0].url,
        且历史行为不发送也能拿到 URL, 故默认不发送以兼容 2.0, 避免回归。
    """

    def build(self, norm: NormImageParams, provider) -> dict:
        payload: dict[str, Any] = {
            "model": provider.model_name,
            "prompt": norm.prompt,
            "n": norm.n,
            "size": norm.size_tier or "2K",   # 档位式, 不用精确像素
        }
        if norm.aspect_ratio:
            if norm.aspect_ratio in _AGNES_RATIOS:
                payload["ratio"] = norm.aspect_ratio
            else:
                logger.warning("[adapter] agnes 不支持的 ratio=%s, 已丢弃", norm.aspect_ratio)
        if norm.seed is not None:
            payload["seed"] = norm.seed
        # 图生图: image 必须进 extra_body, 且不带 tags
        if norm.reference_images:
            payload["extra_body"] = {"image": norm.reference_images}
            logger.info(
                "[adapter] agnes image refs=%d (order preserved, sent via extra_body.image)",
                len(norm.reference_images),
            )
        return payload


class GenericOpenAIImageAdapter(ImageParamAdapter):
    """OpenAI / DALL·E 兼容: size 用精确像素, 不认 ratio。"""

    def build(self, norm: NormImageParams, provider) -> dict:
        tier = norm.size_tier or "1K"
        payload: dict[str, Any] = {
            "model": provider.model_name,
            "prompt": norm.prompt,
            "n": norm.n,
            "size": _TIER_TO_PIXELS.get(tier, "1024x1024"),
        }
        if norm.seed is not None:
            payload["seed"] = norm.seed
        if norm.reference_images:
            payload["image"] = (
                norm.reference_images[0] if len(norm.reference_images) == 1
                else norm.reference_images
            )
        return payload


def get_image_adapter(base_url: str) -> ImageParamAdapter:
    """按提供商族分派。新增模型 = 在此加分支或注册表, 不动 provider。"""
    if "agnes" in (base_url or "").lower():
        return AgnesImageAdapter()
    return GenericOpenAIImageAdapter()
