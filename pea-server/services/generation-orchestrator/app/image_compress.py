"""参考图压缩引擎 (单一职责, 与提供商无关).

为什么单独成模块:
  「把一张图压到 N 字节以内」是纯计算, 不该和参考图解析策略 (param_adapters)、
  HTTP 调用 (agnes_provider) 混在一起。抽出来后:
    - 可单测 (tests/test_image_compress.py), 不需要起容器/连 MinIO;
    - 任何提供商 (Agnes / 火山 / MiniMax / Gemini) 都能复用同一套压缩语义;
    - Pillow 只在真正压缩时才 import, 未触发压缩的正常路径零开销。

核心算法 (相对旧实现 `0.75 盲缩 + quality-10` 的改进):
  阶段 1 「先降质量, 不动分辨率」:
    >10MB 的输入图绝大多数是无损 PNG / 手机原图 (JPEG q≈95~100)。仅仅重编码到
    q=85 通常就能缩到 1/5~1/10, 而肉眼几乎无差 —— 这一步保住了**分辨率**,
    对图生图的细节还原至关重要。旧实现一上来就把画面缩到 75%, 白白丢像素。
  阶段 2 「仍超预算才缩分辨率, 且一次到位」:
    按 sqrt(预算/当前体积) 估算缩放系数 (JPEG 体积近似正比于像素数), 一次缩到位,
    而不是 0.75 一档档试 —— 少 3~4 轮编码, 也不会过冲把 4000px 砍到 1200px。
  质量二分:
    在 [min_quality, max_quality] 内二分找「不超预算的最高质量」, 5 次探测即可把
    质量定到 ±1 —— 比线性 -10 一档档降精细得多, 同样体积下画质更好。

其它工程细节:
  - EXIF 方向校正 (ImageOps.exif_transpose): 手机竖拍图重编码后不会躺倒;
  - 元数据剥离: 不写 EXIF/ICC, 单张能白省几百 KB;
  - 透明通道: 有 alpha 时优先 WebP (保 alpha 且同质量比 JPEG 小 25%~35%),
    Pillow 不支持 WebP 时回退 JPEG 并铺白底 (避免透明区变黑块);
  - 返回 CompressResult 而非裸 bytes: 调用方能把「压前/压后/尺寸/质量/轮数」
    打进日志, 出问题时一眼看出是不是压过头了 (可观测性 > 省两行代码)。
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

# base64 膨胀: 原图 n 字节 -> 线上 ((n+2)//3)*4 字节 (约 4/3)。
# 内联参考图是以 data: URI 放进 JSON 体发送的, 上游数的是这串文本, 故所有
# 「线上预算 -> 原图预算」的换算都必须过这里, 不能拿解码字节直接比。
def wire_len(raw_len: int) -> int:
    """原图字节数 -> base64 线上字节数 (含 padding)。"""
    return ((raw_len + 2) // 3) * 4


def raw_budget_from_wire(wire_budget: int) -> int:
    """线上字节预算 -> 原图字节预算 (反推, 保证编码后不超预算)。"""
    return int(wire_budget * 3 / 4)


# 上游「图片过大」类错误的特征词。命中即触发一次「压缩后重试」自愈。
# ★ 覆盖中英文与 HTTP 语义三类:
#   - 中文: Agnes 实测报文形如「图片超过10m」;
#   - 英文: image too large / exceeds maximum size / file size limit;
#   - HTTP: 413 Payload Too Large / Request Entity Too Large。
_OVERSIZE_PATTERNS = (
    r"图片\s*(大小)?\s*(超过|过大|不能超过|超出)",
    r"图像\s*(大小)?\s*(超过|过大|超出)",
    r"文件\s*(大小)?\s*(超过|过大|超出)",
    r"too\s+large",
    r"exceed(s|ed)?\s+.{0,24}(size|limit|bytes|mb)",
    r"(size|payload|body|entity|image)\s+.{0,16}(exceed|limit|too\s+big)",
    r"maximum\s+.{0,16}(size|bytes)",
    r"payload\s+too\s+large",
    r"request\s+entity\s+too\s+large",
    r"\b413\b",
    r"\bfile_size\b",
    r"image_too_large",
)
_OVERSIZE_RE = re.compile("|".join(_OVERSIZE_PATTERNS), re.IGNORECASE)


def looks_like_oversize_error(text: Any) -> bool:
    """判断上游报错是否属于「输入图太大」。

    只在**明确**命中特征词时返回 True —— 宁可漏判 (退化为原样失败, 用户看到真实错误),
    也不要误判 (把无关错误当成大小问题去压缩重试, 白烧一次额度还掩盖真实原因)。
    """
    if not text:
        return False
    return bool(_OVERSIZE_RE.search(str(text)))


@dataclass
class CompressResult:
    """压缩结果 + 全过程指标 (供日志/诊断; 不要只返回 bytes)。"""

    data: bytes
    mime: str
    width: int
    height: int
    quality: int
    scale: float          # 相对原图的边长缩放比 (1.0 = 未缩分辨率)
    rounds: int           # 实际编码次数 (性能观测)
    original_bytes: int
    ok: bool              # 是否压进了预算 (False = 尽力而为, 调用方需走兜底)

    @property
    def data_len(self) -> int:
        return len(self.data)

    @property
    def ratio(self) -> float:
        return (len(self.data) / self.original_bytes) if self.original_bytes else 1.0

    def summary(self) -> str:
        return (
            f"{self.original_bytes / 1024 / 1024:.2f}MB -> {self.data_len / 1024 / 1024:.2f}MB "
            f"({self.ratio * 100:.0f}%), {self.width}x{self.height}, "
            f"{self.mime.split('/')[-1]} q={self.quality}, scale={self.scale:.2f}, "
            f"rounds={self.rounds}, ok={self.ok}"
        )


def _has_alpha(img) -> bool:
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def _webp_available() -> bool:
    try:
        from PIL import features

        return bool(features.check("webp"))
    except Exception:  # noqa: BLE001
        return False


def _encode(img, fmt: str, quality: int) -> bytes:
    """编码到内存。统一剥离元数据 (不写 exif/icc), 单张可省几百 KB。"""
    buf = BytesIO()
    if fmt == "WEBP":
        img.save(buf, format="WEBP", quality=quality, method=4)
    else:
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def _flatten(img, fmt: str):
    """JPEG 不支持 alpha: 铺白底合成, 避免透明区被渲染成黑块。"""
    if fmt == "JPEG" and _has_alpha(img):
        from PIL import Image

        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        return bg
    if fmt == "JPEG":
        return img.convert("RGB")
    return img


def compress_to_budget(
    raw: bytes,
    max_bytes: int,
    *,
    max_edge: int | None = None,
    min_quality: int = 62,
    max_quality: int = 92,
    max_scale_rounds: int = 3,
) -> CompressResult:
    """把图片字节压到 ``<= max_bytes``, 尽量保住分辨率与画质。

    Args:
        raw: 原始图片字节。
        max_bytes: 目标上限 (**原图字节**, 非 base64 线上字节; 线上预算请先过
            ``raw_budget_from_wire``)。
        max_edge: 最长边硬上限 (像素)。None = 不主动限制, 只在超预算时才缩。
            传值可用于「顺手把 8000px 的图收到 4096px」这类稳定性需求。
        min_quality: 质量下限, 低于此值宁可缩分辨率也不再降质量 (62 是 JPEG
            肉眼可接受的下沿; 再低会出块效应, 图生图会把噪声一并学过去)。
        max_quality: 质量上限。>92 对体积收益极差 (体积翻倍, 观感几乎不变)。
        max_scale_rounds: 分辨率缩放的最大轮数。

    Returns:
        CompressResult; ``ok=False`` 表示尽力而为仍超预算 (极端小预算),
        调用方应走兜底 (如改走公网 URL 投递)。

    Raises:
        ImportError: 环境缺 Pillow (调用方应捕获并降级)。
        OSError / ValueError: 图片解码失败 (非图片数据/损坏)。
    """
    from PIL import Image, ImageOps

    original_bytes = len(raw)
    if max_bytes <= 0:
        raise ValueError("max_bytes 必须为正数")

    img = Image.open(BytesIO(raw))
    img = ImageOps.exif_transpose(img)          # 手机竖拍图重编码后不躺倒
    src_w, src_h = img.size

    keep_alpha = _has_alpha(img) and _webp_available()
    fmt = "WEBP" if keep_alpha else "JPEG"
    mime = "image/webp" if fmt == "WEBP" else "image/jpeg"
    work = _flatten(img, fmt)

    # 主动收敛超大分辨率 (可选): 这一步不算"压缩过头", 纯粹是把 8000px 这类
    # 极端输入拉回可编码范围, 顺带让后续每轮编码快得多。
    scale = 1.0
    if max_edge and max(src_w, src_h) > max_edge:
        scale = max_edge / max(src_w, src_h)
        work = work.resize(
            (max(1, round(src_w * scale)), max(1, round(src_h * scale))),
            Image.LANCZOS,
        )

    rounds = 0
    best: tuple[bytes, int] | None = None      # (bytes, quality) 满足预算的最优解
    smallest: tuple[bytes, int] | None = None  # 兜底: 见过的最小一版

    def probe(image, quality: int) -> bytes:
        nonlocal rounds, smallest
        out = _encode(image, fmt, quality)
        rounds += 1
        if smallest is None or len(out) < len(smallest[0]):
            smallest = (out, quality)
        return out

    for scale_round in range(max_scale_rounds + 1):
        # ── 质量二分: 找「不超预算的最高质量」──────────────────────────
        lo, hi = min_quality, max_quality
        local_best: tuple[bytes, int] | None = None
        # 先探上界: 最高质量就已达标 -> 直接收工 (最常见: 无损 PNG 转 q92 JPEG)
        out = probe(work, hi)
        if len(out) <= max_bytes:
            local_best = (out, hi)
        else:
            # 再探下界: 最低质量都超 -> 本轮分辨率下无解, 交给缩放轮
            out_lo = probe(work, lo)
            if len(out_lo) <= max_bytes:
                local_best = (out_lo, lo)
                while lo + 1 < hi:
                    mid = (lo + hi) // 2
                    out_mid = probe(work, mid)
                    if len(out_mid) <= max_bytes:
                        local_best = (out_mid, mid)
                        lo = mid
                    else:
                        hi = mid
        if local_best:
            best = local_best
            break
        if scale_round >= max_scale_rounds:
            break
        # ── 分辨率缩放: 按体积∝像素数 反推系数, 一次到位 (留 8% 余量) ────
        cur = smallest[0] if smallest else out
        factor = (max_bytes / max(1, len(cur))) ** 0.5 * 0.92
        factor = max(0.35, min(0.9, factor))   # 单轮最多砍到 35%, 避免过冲
        new_w = max(64, round(work.width * factor))
        new_h = max(64, round(work.height * factor))
        if (new_w, new_h) == work.size:
            break
        work = work.resize((new_w, new_h), Image.LANCZOS)
        scale = work.width / src_w

    if best:
        data, quality = best
        ok = True
    else:
        data, quality = smallest if smallest else (raw, max_quality)
        ok = len(data) <= max_bytes

    result = CompressResult(
        data=data,
        mime=mime,
        width=work.width,
        height=work.height,
        quality=quality,
        scale=round(scale, 4),
        rounds=rounds,
        original_bytes=original_bytes,
        ok=ok,
    )
    logger.info("[img-compress] %s", result.summary())
    return result


# ── data: URI 便捷封装 ───────────────────────────────────────────────────────
_DATA_URI_RE = re.compile(r"data:([^;,]+);base64,(.+)", re.DOTALL)


def split_data_uri(uri: str) -> tuple[str, bytes]:
    """data: URI -> (mime, 解码后字节)。非法格式抛 ValueError。"""
    m = _DATA_URI_RE.match(uri)
    if not m:
        raise ValueError("not a base64 data URI")
    body = m.group(2)
    pad = (-len(body)) % 4          # 补齐 padding, 容忍上游/前端裁掉 '='
    if pad:
        body += "=" * pad
    return m.group(1), base64.b64decode(body)


def build_data_uri(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def compress_data_uri_to_wire_budget(
    uri: str, wire_budget: int, **kwargs
) -> tuple[str, CompressResult | None]:
    """把 data: URI 压到「线上 base64 字节 <= wire_budget」。

    返回 (新的 data URI, 压缩报告)。已在预算内则原样返回, 报告为 None
    —— 调用方据此区分「没动过」与「压过了」, 便于日志和计费口径。
    """
    mime, raw = split_data_uri(uri)
    if wire_len(len(raw)) <= wire_budget:
        return uri, None
    res = compress_to_budget(raw, raw_budget_from_wire(wire_budget), **kwargs)
    return build_data_uri(res.data, res.mime), res
