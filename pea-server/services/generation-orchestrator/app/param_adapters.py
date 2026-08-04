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

import abc
import base64
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, unquote

from app.config import settings

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

# 参考图单图字节上限（解码后原始字节数）。
# 上游（Agnes / 火山方舟 图像 API）硬限制单张输入图 ≤ 10MB（10485760 bytes）；
# 此处取 8MB 留 2MB headroom，避免 JPEG 元信息/边界抖动触发上游 10MB 上限。
# ★ 单一真相源：UI / 客户端 / 后端三处应共用此值（前端 EcommerceGallery 文案 10MB、
# galleryApi MAX_FILE_BYTES=8MB 后续应与此对齐，避免数字分裂）。
MAX_REF_IMAGE_BYTES = 8 * 1024 * 1024
# 降采样目标：比上限再小一档，确保 re-encode 后稳稳低于上限。
_REF_DOWNSAMPLE_TARGET_BYTES = int(MAX_REF_IMAGE_BYTES * 0.8)


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
    return _resolve_internal_ref_key(raw_key)


def _resolve_internal_ref_key(raw_key: str) -> str | None:
    """用 MinIO 客户端直下指定 key 并转为 base64 data: URI。

    同时尝试 url-decoded 与原样两种 key 形态, 兼容 percent-encoding 差异。
    """
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
                resp = client.get_object(settings.minio_bucket, key)
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
    2. 检测到内部 URL（localhost / 私有 IP / 容器名 / 非标准端口）或
       本站 CDN 相对路径 /media/<key> 时, 通过编排器自有 MinIO 客户端下载并
       转为 base64 data: URI（外部模型可直接消费；视频接口会进一步转公网 URL）;
    3. blob: 等不可达地址丢弃。
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
        elif r.startswith('/media/'):
            # 本站公开 CDN 相对路径: nginx 把 /media/ 代理到 MinIO bucket,
            # 去掉前缀即 object key。AI 生成图落库后以此形式存于节点 resultUrl。
            key = unquote(r[len('/media/'):])
            converted = _resolve_internal_ref_key(key)
            if converted:
                out.append(converted)
                resolved_internal += 1
            else:
                dropped += 1
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
        # 仅做基础规整; 真正的 base64/公网解析交由适配器声明的 ref_strategy 在 provider 层执行。
        reference_images=_clean_ref_list(p.get("reference_images")),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 参考图解析策略 (Strategy Pattern)
# ─────────────────────────────────────────────────────────────────────────────
# 外部模型对"参考图"的喂法分两类:
#   1) 支持内联 base64 (Agnes 图像 API 的 extra_body.image[] 数组): 直接把图片
#      base64 内联进请求体, 完全不经过公网存储 —— 内网/localhost 图片也能用,
#      无需配置 PEA_CDN_BASE_URL / 隧道。
#   2) 只认 http(s) URL (Agnes 视频 API 的 image 字段): 必须把参考图转存到
#      外部模型可下载的公网地址, 否则下载不到 (走 PEA_EXTERNAL_REF_BASE_URL/CDN 兜底)。
#
# 把"怎么解析参考图"抽象成策略, 由每个 ImageParamAdapter 声明自己用哪种,
# 新增模型 = 选一个策略(或自定义), 不污染 provider 主流程。
# ─────────────────────────────────────────────────────────────────────────────

class ReferenceResolutionStrategy(abc.ABC):
    """参考图解析策略: 把前端/API 给的任意形式参考图, 解析成该模型能消费的形式。"""

    @abc.abstractmethod
    def resolve(self, refs: Any, provider: Any = None) -> list[str]:
        ...


def _split_data_uri(ref: str) -> tuple[str, str]:
    """从 data: URI 拆出 (mime, base64_body)；非标准 data URI 抛 ValueError。"""
    m = re.match(r"data:([^;]+);base64,(.+)", ref, re.DOTALL)
    if not m:
        raise ValueError("not a data URI")
    return m.group(1), m.group(2)


def _data_uri_of(raw: bytes, mime: str = "image/jpeg") -> str:
    """字节 -> data: URI。"""
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _downsample_image_bytes(raw: bytes, max_bytes: int) -> bytes:
    """把图片原始字节降采样/重编码到 ≤ max_bytes（输出 JPEG）。

    用于参考图超过上游大小上限前的边界护栏：先尽量保留内联（保隐私），
    仅当降采样后仍超限才退化为公网 URL 投递（见 Base64InlineStrategy）。
    依赖 Pillow；缺失时抛 ImportError，由调用方降级到 URL 兜底。
    """
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(raw)).convert("RGB")
    quality = 85
    scale = 1.0
    last: bytes | None = None
    for _ in range(8):
        w = max(1, int(img.width * scale))
        h = max(1, int(img.height * scale))
        tmp = img.resize((w, h), Image.LANCZOS)
        buf = BytesIO()
        tmp.save(buf, format="JPEG", quality=quality, optimize=True)
        out = buf.getvalue()
        if len(out) <= max_bytes:
            return out
        last = out
        scale *= 0.75
        if quality > 60:
            quality -= 10
    # 尽力而为：返回最小的一版（仍可能超上限，调用方再走 URL 兜底）
    return last or out


class Base64InlineStrategy(ReferenceResolutionStrategy):
    """策略 A: 内联 base64 (图片类模型适用, 如 Agnes 图像 API).

    - data: URI 未超上限时原样保留;
    - 内部/相对 URL (localhost / 私有 IP / /media/<key>) 经编排器自有 MinIO 客户端
      直下, 转 base64 data URI; 外部模型直接消费内联 base64;
    - 公网 http(s) URL 原样保留 (模型自行拉取);
    - ★ 边界护栏（2026-08-04 新增）: 单张解码后字节 > MAX_REF_IMAGE_BYTES 时,
      先用 Pillow 降采样到 ≤ 上限（仍内联, 保隐私, 真正打穿上游 10MB 上限）；
      若降采样后仍超限（极端长图）或 Pillow 不可用, 则退化为公网 URL 投递
      （provider.resolve_refs —— 复用视频链路的 store_bytes 上传 + 可达性预检）,
      即用户要的「照片大于阈值就走连接兜底」。
    仅触发 URL 兜底分支时才调用 storage.store_bytes 上传公开存储。
    """

    def resolve(self, refs: Any, provider: Any = None) -> list[str]:
        out: list[str] = []
        for r in _normalize_refs(refs):
            if not r.startswith("data:"):
                # 公网 URL: 直接透传, 由模型自行拉取（不在此下载做大小预检）。
                out.append(r)
                continue
            # data: URI: 解析解码后字节数
            try:
                _mime, b64 = _split_data_uri(r)
                raw = base64.b64decode(b64)
            except Exception:
                # 非标准 data URI 原样保留, 交给上游判错。
                out.append(r)
                continue
            if len(raw) <= MAX_REF_IMAGE_BYTES:
                out.append(r)
                continue
            # 超阈值: 先降采样（尽量保内联）
            smaller: bytes | None = None
            try:
                smaller = _downsample_image_bytes(raw, _REF_DOWNSAMPLE_TARGET_BYTES)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[refs] 参考图降采样失败 (将退化为公网 URL 兜底): %s", exc)
            if smaller and len(smaller) <= MAX_REF_IMAGE_BYTES:
                out.append(_data_uri_of(smaller, "image/jpeg"))
                continue
            # 降采样后仍超限 或 不可用 -> 走连接兜底: 上传公开存储, 返回公网 URL
            if provider is not None:
                try:
                    src = _data_uri_of(smaller, "image/jpeg") if smaller else r
                    url = provider.resolve_refs([src])[0]
                    out.append(url)
                    logger.info(
                        "[refs] 参考图超阈值已走公网 URL 兜底 (%d bytes -> %s)",
                        len(raw), url[:120],
                    )
                    continue
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[refs] 公网 URL 兜底失败, 仍内联原图: %s", exc)
            # 兜底也失败: 保留原内联（上游若仍超限会返回明确错误, 不再静默泛化）
            out.append(r)
        return out


class PublicUrlStrategy(ReferenceResolutionStrategy):
    """策略 B: 转公网 URL (视频类模型适用, 如 Agnes 视频 API 只认 http(s)).

    data:/内部 URL 先经 Base64Inline 转 base64, 再由 provider.resolve_refs
    转存到公开存储, 返回 Agnes 可下载的公网 URL (走 PEA_EXTERNAL_REF_BASE_URL/CDN)。
    需要 provider 提供 resolve_refs (OpenAICompatibleProvider / BaseProviderAdapter 均有默认实现)。
    """

    def resolve(self, refs: Any, provider: Any = None) -> list[str]:
        if provider is None:
            raise RuntimeError("PublicUrlStrategy 需要 provider 以访问 resolve_refs")
        return provider.resolve_refs(_normalize_refs(refs))


def _clean_ref_list(refs: Any) -> list[str]:
    """基础规整: 字符串/列表归一、丢弃非字符串/空白、限 8 张。

    不做 base64 转换 —— 转换交由适配器声明的 ref_strategy 在 provider 层执行
    (这样"用哪种策略"由适配器单一决定, 而非散在 normalize 里)。
    """
    if not refs:
        return []
    if isinstance(refs, str):
        refs = [refs]
    out: list[str] = []
    for r in list(refs)[:8]:
        if isinstance(r, str) and r.strip():
            out.append(r)
    return out


class ImageParamAdapter:
    # 参考图解析策略: 图片模型默认内联 base64 (不经公网); 视频类需覆写为 PublicUrlStrategy。
    ref_strategy: ReferenceResolutionStrategy = Base64InlineStrategy()

    def build(self, norm: NormImageParams, provider) -> dict:
        raise NotImplementedError


class AgnesImageAdapter(ImageParamAdapter):
    """Agnes 2.x 图像: 档位式 size + ratio + extra_body.image, 不发 tags。

    图像 API 的 extra_body.image[] 数组接受 base64 data URI, 故用 Base64InlineStrategy
    —— 内网/localhost 参考图经 MinIO 直下转 base64 内联, **无需公网**。

    官方文档要点:
      - size 推荐 "1K".."4K" 档位, 配合 ratio 得到可预期尺寸 (2K+16:9 -> 2624x1472)。
      - 图生图 image 放 extra_body.image; 不要传 tags:["img2img"]。
      - response_format 必须在 extra_body 内 (顶层会 400); 但我们直接读 data[0].url,
        且历史行为不发送也能拿到 URL, 故默认不发送以兼容 2.0, 避免回归。
    """

    ref_strategy = Base64InlineStrategy()

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
        # 官方要求 response_format 必须放 extra_body 内 (顶层会 400)。
        # 显式请求 url 输出, 避免上游默认返回 b64_json 巨块 -> 破坏 URL 直存/显示链路。
        extra: dict[str, Any] = {"response_format": "url"}
        # 图生图: image 必须进 extra_body, 且不带 tags
        if norm.reference_images:
            extra["image"] = norm.reference_images
            logger.info(
                "[adapter] agnes image refs=%d (order preserved, sent via extra_body.image)",
                len(norm.reference_images),
            )
        payload["extra_body"] = extra
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
