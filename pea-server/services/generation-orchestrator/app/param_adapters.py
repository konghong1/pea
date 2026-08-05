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
import requests
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

# ─────────────────────────────────────────────────────────────────────────────
# 参考图字节预算：Agnes 已接线（env 可调），其余提供商仍不设限
# ─────────────────────────────────────────────────────────────────────────────
# ★ 演进史（三次反复，值得记住）：
#   - 初版：硬编码 8MB「解码字节」护栏 —— 漏算 base64 膨胀 33%，8MB 原图线上 10.67MB，
#           反而打穿了 10MB 上限（错在计量口径）。
#   - 2026-08-04：实测 >10MB 也能出图，判定「限制不存在」，整条护栏撤下（错在把
#           一次抽样当结论）。
#   - 2026-08-05：再次踩到「单张图片不能超过 10m」。结论不是「到底限不限」，而是
#           **上游的规矩我们无法稳定观测**。于是改成两道互补防线，且都不写死：
#             ① 主动护栏（本节）：按 env 配置的上限，在发出前把超限图压进预算；
#             ② 被动自愈（agnes_provider._call_image_with_oversize_retry）：上游明确
#                回「图太大」时，自动压缩后重试一次。
#           ①失准也有②兜底，②生效则说明①的阈值该调 —— 调 env 即可，无需改代码。
#
#   计量口径（务必记牢）：内联参考图以 base64 data URI 放进 JSON 体发送，上游数的是
#   那串**线上字节** = 原图 × 4/3；而 URL 投递由上游自行下载，数的是**原始文件字节**。
#   两种口径分别对应 inline_wire_limit() / source_bytes_limit()，不能混用。
AGNES_UPSTREAM_REF_IMAGE_LIMIT_BYTES = settings.agnes_ref_image_limit_bytes
AGNES_REF_IMAGE_HEADROOM_BYTES = settings.agnes_ref_image_headroom_bytes

# 向后兼容别名（历史代码/测试可能引用；新代码请改用 adapter.ref_strategy.budget）。
UPSTREAM_REF_IMAGE_LIMIT_BYTES = AGNES_UPSTREAM_REF_IMAGE_LIMIT_BYTES


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


def _base64_len(n: int) -> int:
    """base64 编码后（含 padding）的字节数：原图 n 字节 → 线上 (n+2)//3*4 字节。

    内联参考图以 data: URI 发送，上游实际收到的就是这串 base64 文本，故护栏必须按它判断，
    否则会漏算 33% 膨胀（旧实现 8MB 原图 → 10.67MB 线上 → 打穿上游 10MB 上限）。
    """
    return ((n + 2) // 3) * 4


# ─────────────────────────────────────────────────────────────────────────────
# 参考图字节预算适配层 (SPI)
# ─────────────────────────────────────────────────────────────────────────────
class RefImageBudget(abc.ABC):
    """接口: 单张参考图的字节预算契约（每家提供商各自实现, 互不影响）。

    为什么要这层:
      各家上游对「单张输入图多大」的规矩完全不同, 而且**计量口径也不同**:
        - 内联 base64 投递: 上游数的是请求体里那串 base64 文本 → 「线上字节」(= 原图 × 4/3);
        - 公网 URL 投递:    上游自己去下载 → 数的是「原始文件字节」(无膨胀)。
      早期把 Agnes 的 10MB 写成模块级常量, 被所有 provider 共用, 等于「一把尺子量五家」:
      对上限更宽的家白白降采样掉画质, 对上限更严的家又拦不住。
      故把「预算」抽象成接口, 由适配器在类上显式声明 —— 谁的规矩谁负责, 新接提供商时
      有明确的填空位, 不会默认继承别家的数字。

    契约 (对应 Java interface 的抽象方法):
      - inline_wire_limit():   内联 base64 的线上字节上限; None = 不限
      - source_bytes_limit():  URL 投递时的原始文件字节上限; None = 不限
    其余方法是带默认实现的便利方法 (对应 Java 8 default method), 通常无需覆写。
    """

    #: 用于日志/诊断的可读名称
    name: str = "unnamed"

    @abc.abstractmethod
    def inline_wire_limit(self) -> int | None:
        """内联 base64 data URI 的**线上字节**上限; 返回 None 表示不限。"""
        ...

    @abc.abstractmethod
    def source_bytes_limit(self) -> int | None:
        """公网 URL 投递时上游按**原始文件字节**判定的上限; 返回 None 表示不限。"""
        ...

    # ── default methods ──────────────────────────────────────────────────────
    @property
    def enforced(self) -> bool:
        """是否需要执行护栏。两个上限都为 None 时可整条跳过, 省掉降采样/HEAD 预检开销。"""
        return self.inline_wire_limit() is not None or self.source_bytes_limit() is not None

    def accepts_inline(self, raw_bytes_len: int) -> bool:
        """给定原图解码字节数, 判断内联投递是否在预算内（内部换算 base64 膨胀）。"""
        limit = self.inline_wire_limit()
        return limit is None or _base64_len(raw_bytes_len) <= limit

    def accepts_source(self, source_bytes_len: int) -> bool:
        """给定原始文件字节数, 判断 URL 投递是否在预算内。"""
        limit = self.source_bytes_limit()
        return limit is None or source_bytes_len <= limit

    def downsample_target_bytes(self) -> int | None:
        """降采样目标（原图像素字节上限）。按 base64 膨胀反推, 保证重编码后线上 ≤ 预算。

        无内联上限时返回 None —— 调用方据此跳过降采样, 保留原始画质。
        """
        limit = self.inline_wire_limit()
        return None if limit is None else int(limit * 3 / 4)

    def __repr__(self) -> str:  # pragma: no cover - 诊断用
        return f"<{type(self).__name__} name={self.name} inline={self.inline_wire_limit()} src={self.source_bytes_limit()}>"


class UnlimitedRefBudget(RefImageBudget):
    """实现 A（默认 / NullObject）: 不设限, 由上游自行判定。

    ★ 除 Agnes 外的所有提供商都用它 —— 我们不替上游猜它的规矩:
      猜松了拦不住（照样报错, 还多绕一圈）, 猜紧了白降画质（更糟, 且用户无感知）。
      让上游返回明确错误, 远好过我们静默压缩。
    """

    name = "unlimited"

    def inline_wire_limit(self) -> int | None:
        return None

    def source_bytes_limit(self) -> int | None:
        return None


class FixedRefBudget(RefImageBudget):
    """实现 B: 固定上限（用于确有硬限制、且已实测确认的提供商）。

    Args:
        name: 诊断用名称, 建议用提供商 key。
        upstream_limit_bytes: 上游文档/实测的硬上限。
        headroom_bytes: 预留余量, 避免 JPEG 元信息/边界抖动刚好踩线; 默认 1MB。
        applies_to_source: 上游对「URL 投递」是否同样按此上限判定。
            Agnes 两种投递都判, 故为 True; 某些家只限制请求体大小时应设 False。
    """

    def __init__(
        self,
        name: str,
        upstream_limit_bytes: int,
        headroom_bytes: int = 1024 * 1024,
        applies_to_source: bool = True,
    ) -> None:
        if headroom_bytes >= upstream_limit_bytes:
            raise ValueError("headroom_bytes 必须小于 upstream_limit_bytes")
        self.name = name
        self.upstream_limit_bytes = upstream_limit_bytes
        self.headroom_bytes = headroom_bytes
        self.applies_to_source = applies_to_source

    def inline_wire_limit(self) -> int | None:
        return self.upstream_limit_bytes - self.headroom_bytes

    def source_bytes_limit(self) -> int | None:
        # URL 投递由上游自行下载, 不经 base64 膨胀, 故直接按硬上限判（无需 headroom）。
        return self.upstream_limit_bytes if self.applies_to_source else None


#: 默认预算：不限。所有未显式声明的提供商都用它。
UNLIMITED_REF_BUDGET = UnlimitedRefBudget()

def make_env_ref_budget(name: str, limit_bytes: int, headroom_bytes: int) -> RefImageBudget:
    """按 env 配置构造预算; ``limit_bytes <= 0`` 视为「关闭护栏」-> 返回不限预算。

    为什么要工厂而不是直接 new: 上限来自环境变量, 运维可能填 0 (关闭) 或填一个
    小于 headroom 的值。工厂负责把这些边界收敛成合法对象, 而不是让服务在 import
    阶段抛 ValueError 起不来 —— 配置错误不该导致整个编排器无法启动。
    """
    if limit_bytes <= 0:
        return UNLIMITED_REF_BUDGET
    headroom = headroom_bytes
    if headroom >= limit_bytes:            # 配置不合理时退化为 10% 余量, 并告警
        headroom = max(1, limit_bytes // 10)
        logger.warning(
            "[refs][%s] headroom(%d) >= limit(%d), 已自动收敛为 %d",
            name, headroom_bytes, limit_bytes, headroom,
        )
    return FixedRefBudget(name=name, upstream_limit_bytes=limit_bytes,
                          headroom_bytes=headroom)


#: Agnes 参考图预算（**已接线**）。默认「单图 ≤ 10MB 线上字节 + 1MB headroom」= 内联预算 9MB。
#  运维可通过 PEA_AGNES_REF_IMAGE_LIMIT_BYTES 调整; 置 0 = 关闭主动护栏, 只留被动自愈。
AGNES_REF_BUDGET = make_env_ref_budget(
    "agnes",
    AGNES_UPSTREAM_REF_IMAGE_LIMIT_BYTES,
    AGNES_REF_IMAGE_HEADROOM_BYTES,
)

#: 预算注册表（类 Java SPI）: provider key -> 预算实现。未注册者一律 UNLIMITED_REF_BUDGET。
#  只登记**已被实测证实**存在硬限的提供商; 其余交上游判定 —— 猜松了拦不住, 猜紧了白降画质。
_REF_BUDGET_REGISTRY: dict[str, RefImageBudget] = {
    "agnes": AGNES_REF_BUDGET,
}


def register_ref_budget(provider_key: str, budget: RefImageBudget) -> None:
    """注册某提供商的参考图预算。新接入的提供商若确有硬限制, 在此登记（或直接在适配器上声明）。"""
    if not isinstance(budget, RefImageBudget):
        raise TypeError("budget 必须实现 RefImageBudget 接口")
    _REF_BUDGET_REGISTRY[provider_key.lower()] = budget


def get_ref_budget(provider_key: str | None) -> RefImageBudget:
    """按提供商 key 取预算; 未注册返回 UNLIMITED_REF_BUDGET（不限）。"""
    if not provider_key:
        return UNLIMITED_REF_BUDGET
    return _REF_BUDGET_REGISTRY.get(provider_key.lower(), UNLIMITED_REF_BUDGET)


def _guard_url_ref(url: str, provider: Any = None,
                   budget: RefImageBudget = UNLIMITED_REF_BUDGET) -> str:
    """公网 URL 参考图的大小护栏（fail-open）。

    上游按「原始文件字节数」判上限（URL 图由上游自行下载，不经过 base64 膨胀，
    故直接比原始大小）。能拿到 Content-Length 且超限时，下载 → Pillow 降采样 →
    经 provider.resolve_refs 转存为公网 URL 再回传；拿不到大小 / 降采样失败 / 任何异常
    则原样透传，交上游最终判定 —— 绝不误伤正常图。

    ★ budget 无 source 上限时（默认，即 Agnes 之外的所有提供商）直接透传：
      连 HEAD 预检都不发，零额外开销、零画质损失。
    仅当 provider 可用（图片适配器总会带 provider）时才做转存兜底；否则超限也透传。
    """
    src_limit = budget.source_bytes_limit()
    if src_limit is None:
        return url
    target = budget.downsample_target_bytes()
    try:
        head = requests.head(
            url, timeout=(settings.provider_http_connect_timeout_s, 20),
            allow_redirects=True, proxies={"http": None, "https": None},
        )
        cl = head.headers.get("Content-Length")
        if cl and int(cl) > src_limit:
            resp = requests.get(
                url, timeout=(settings.provider_http_connect_timeout_s, 60),
                proxies={"http": None, "https": None},
            )
            resp.raise_for_status()
            raw = resp.content
            if len(raw) <= src_limit:
                return url  # HEAD 报大、实际小（压缩传输）则透传
            smaller = _downsample_image_bytes(raw, target or src_limit)
            if provider is not None and smaller:
                rehosted = provider.resolve_refs([_data_uri_of(smaller, "image/jpeg")])
                if rehosted:
                    logger.info("[refs] URL 参考图超阈值已下载降采样并转存 (%d bytes -> %s)",
                                len(raw), rehosted[0][:120])
                    return rehosted[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[refs] URL 参考图大小预检失败(透传交上游判定): %s | %s", url[:120], exc)
    return url


def _downsample_image_bytes(raw: bytes, max_bytes: int) -> bytes:
    """把图片原始字节压到 ≤ max_bytes（薄封装, 真正的算法在 app.image_compress）。

    保留此函数名是为了兼容既有调用点与单测 (它们会 mock 这个符号)。
    实现已换成「先降质量保分辨率, 再按面积一次缩到位 + 质量二分」的压缩引擎:
    同样体积下画质明显更好, 编码轮数也更少 (详见 image_compress 模块 docstring)。

    依赖 Pillow；缺失时抛 ImportError，由调用方降级到 URL 兜底。
    """
    from app.image_compress import compress_to_budget

    res = compress_to_budget(raw, max_bytes, max_edge=settings.ref_compress_max_edge)
    return res.data


class Base64InlineStrategy(ReferenceResolutionStrategy):
    """策略 A: 内联 base64 (图片类模型适用, 如 Agnes 图像 API).

    - data: URI 未超上限时原样保留;
    - 内部/相对 URL (localhost / 私有 IP / /media/<key>) 经编排器自有 MinIO 客户端
      直下, 转 base64 data URI; 外部模型直接消费内联 base64;
    - 公网 http(s) URL 走 fail-open 大小预检 (_guard_url_ref): 已知超限才下载+降采样+转存,
      拿不到大小则原样透传交上游判定;
    - ★ 边界护栏由构造注入的 RefImageBudget 决定, **不再硬编码**:
        Base64InlineStrategy()                    -> 不限 (默认, **当前全部提供商**)
        Base64InlineStrategy(AGNES_REF_BUDGET)    -> 内联线上 ≤ 9MB / 源文件 ≤ 10MB (备用)
      有上限时: 内联图按「线上 base64 字节」判断（见 _base64_len）而非解码字节 —— 这是
      base64 膨胀 33% 的必然要求（8MB 原图 → 线上 ~10.67MB）; 超预算先用 Pillow 降采样
      （仍内联, 保隐私）, 降采样后仍超限或 Pillow 不可用则退化为公网 URL 投递
      （provider.resolve_refs —— 复用视频链路的 store_bytes 上传 + 可达性预检）。
      不限时: 原图原样内联, 不解码、不降采样、不发 HEAD —— 零开销零画质损失。
    仅触发 URL 兜底分支时才调用 storage.store_bytes 上传公开存储。
    """

    def __init__(self, budget: RefImageBudget = UNLIMITED_REF_BUDGET) -> None:
        if not isinstance(budget, RefImageBudget):
            raise TypeError("budget 必须实现 RefImageBudget 接口")
        self.budget = budget

    def resolve(self, refs: Any, provider: Any = None) -> list[str]:
        budget = self.budget
        normalized = _normalize_refs(refs)
        # 快路径: 无任何上限 -> 原样投递, 不解码/不降采样/不发 HEAD 预检。
        if not budget.enforced:
            return normalized
        out: list[str] = []
        for r in normalized:
            if not r.startswith("data:"):
                # 公网 URL: fail-open 大小预检（已知超限才下载+降采样+转存；拿不到大小则透传）。
                out.append(_guard_url_ref(r, provider, budget))
                continue
            # data: URI: 解析解码后字节数
            try:
                _mime, b64 = _split_data_uri(r)
                raw = base64.b64decode(b64)
            except Exception:
                # 非标准 data URI 原样保留, 交给上游判错。
                out.append(r)
                continue
            # 按「线上 base64 字节」判断（关键修复：旧实现按解码字节, 漏算 33% 膨胀打穿上限）。
            if budget.accepts_inline(len(raw)):
                out.append(r)
                continue
            # 超阈值: 先降采样（尽量保内联）
            smaller: bytes | None = None
            target = budget.downsample_target_bytes()
            try:
                if target is not None:
                    smaller = _downsample_image_bytes(raw, target)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[refs] 参考图降采样失败 (将退化为公网 URL 兜底): %s", exc)
            if smaller and budget.accepts_inline(len(smaller)):
                logger.info("[refs][%s] 内联参考图超预算已降采样 (%d -> %d bytes)",
                            budget.name, len(raw), len(smaller))
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
    # ★ 默认预算 = UNLIMITED_REF_BUDGET（不限）: 不替上游猜它的规矩。
    #   某家确有硬限制时, 在其适配器上显式声明 Base64InlineStrategy(FixedRefBudget(...))。
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

    ★ 大小预算: **已启用**, 由 env 驱动 (PEA_AGNES_REF_IMAGE_LIMIT_BYTES, 默认 10MB)。
      超预算的参考图在发出前就地压缩 (仍内联, 不经公网 -> 保隐私); 压完还超才退化为
      公网 URL 投递。置 0 可关闭本护栏, 此时只保留 provider 层的「上游报错后压缩重试」自愈。
      口径: 内联按线上 base64 字节判 (原图 × 4/3), URL 投递按原始文件字节判。
    """

    ref_strategy = Base64InlineStrategy(AGNES_REF_BUDGET)

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
