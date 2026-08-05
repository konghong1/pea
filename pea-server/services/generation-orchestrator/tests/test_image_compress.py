"""参考图压缩引擎单测 (纯计算, 不需要容器/MinIO/网络)。

覆盖三块:
  1. 字节换算与错误识别 (wire_len / raw_budget_from_wire / looks_like_oversize_error);
  2. 压缩语义 (压得进预算、优先保分辨率、alpha 保留、极端小预算尽力而为);
  3. data: URI 封装 (已在预算内不重编码 —— 避免无谓的画质损失)。

运行: python tests/test_image_compress.py  (容器内: python /app/tests/test_image_compress.py)
"""
import base64
import os
import sys
from io import BytesIO

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.image_compress import (  # noqa: E402
    CompressResult,
    build_data_uri,
    compress_data_uri_to_wire_budget,
    compress_to_budget,
    looks_like_oversize_error,
    raw_budget_from_wire,
    split_data_uri,
    wire_len,
)


def _noisy_png(w: int, h: int) -> bytes:
    """造一张「难压」的图: 纯色图会被压到几 KB, 测不出预算逻辑, 故用伪随机噪声。"""
    from PIL import Image

    rnd = os.urandom(w * h * 3)
    img = Image.frombytes("RGB", (w, h), rnd)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _rgba_png(w: int, h: int) -> bytes:
    from PIL import Image

    img = Image.new("RGBA", (w, h), (10, 200, 120, 128))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── 1. 换算与错误识别 ────────────────────────────────────────────────────────
def test_wire_len_matches_real_base64():
    for n in (1, 2, 3, 4, 100, 1024, 999_999):
        raw = b"x" * n
        assert wire_len(n) == len(base64.b64encode(raw)), n


def test_raw_budget_round_trip():
    # 反推出的原图预算, 编码后必须真的不超线上预算
    for wire in (1024, 9 * 1024 * 1024, 6 * 1024 * 1024):
        raw_budget = raw_budget_from_wire(wire)
        assert wire_len(raw_budget) <= wire, wire


def test_oversize_error_matcher_hits():
    hits = [
        "图片超过10m",
        "单张图片大小不能超过 10MB",
        "{'error': 'image too large'}",
        "Payload Too Large",
        "request entity too large",
        "HTTP 413",
        "The image exceeds the maximum size of 10 MB",
        "image_too_large",
    ]
    for h in hits:
        assert looks_like_oversize_error(h), h


def test_oversize_error_matcher_no_false_positive():
    """宁漏勿误: 无关错误绝不能触发压缩重试 (会白烧一次额度并掩盖真实原因)。"""
    misses = [
        "",
        None,
        "rate limit exceeded, retry after 60s per 1 minute",
        "invalid api key",
        "content policy violation",
        "model not found: agnes-image-v9",
        "upstream timeout",
    ]
    for m in misses:
        assert not looks_like_oversize_error(m), m


# ── 2. 压缩语义 ──────────────────────────────────────────────────────────────
def test_compress_hits_budget():
    raw = _noisy_png(1200, 900)
    budget = 120 * 1024
    res = compress_to_budget(raw, budget)
    assert isinstance(res, CompressResult)
    assert res.ok and res.data_len <= budget, res.summary()
    assert res.data_len < len(raw)


def test_compress_prefers_keeping_resolution():
    """预算够时只降质量, 不动分辨率 —— 图生图最怕丢像素。"""
    raw = _noisy_png(800, 600)
    # 噪声图 PNG 很大; 给一个 JPEG q92 能达到的宽松预算
    res = compress_to_budget(raw, max(60 * 1024, len(raw) // 2))
    assert res.ok, res.summary()
    assert res.scale == 1.0, f"不该缩分辨率: {res.summary()}"
    assert (res.width, res.height) == (800, 600), res.summary()


def test_compress_scales_down_when_quality_not_enough():
    """预算极紧时必须缩分辨率, 且仍要压进预算。"""
    raw = _noisy_png(1600, 1200)
    budget = 24 * 1024
    res = compress_to_budget(raw, budget)
    assert res.data_len <= budget, res.summary()
    assert res.scale < 1.0, res.summary()


def test_compress_keeps_alpha_as_webp_when_available():
    from PIL import features

    raw = _rgba_png(600, 400)
    res = compress_to_budget(raw, 40 * 1024)
    if features.check("webp"):
        assert res.mime == "image/webp", res.summary()
    else:
        assert res.mime == "image/jpeg", res.summary()
    assert res.data_len <= 40 * 1024


def test_compress_best_effort_on_impossible_budget():
    """预算小到不可能达成时: 不抛异常, 返回尽力而为的最小版本 + ok=False。"""
    raw = _noisy_png(1000, 1000)
    res = compress_to_budget(raw, 512)
    assert res.ok is False, res.summary()
    assert res.data_len < len(raw)


def test_compress_rejects_bad_budget():
    try:
        compress_to_budget(_noisy_png(64, 64), 0)
        assert False, "max_bytes<=0 应抛 ValueError"
    except ValueError:
        pass


def test_compress_bounded_rounds():
    """编码轮数要有上界, 否则大图会把 worker 卡住。"""
    raw = _noisy_png(1400, 1000)
    res = compress_to_budget(raw, 30 * 1024)
    assert res.rounds <= 24, res.summary()


# ── 3. data: URI 封装 ────────────────────────────────────────────────────────
def test_data_uri_round_trip():
    raw = b"\x89PNG\r\n\x1a\n" + b"payload"
    uri = build_data_uri(raw, "image/png")
    mime, back = split_data_uri(uri)
    assert mime == "image/png" and back == raw


def test_data_uri_tolerates_missing_padding():
    raw = b"abcde"
    uri = build_data_uri(raw, "image/png").rstrip("=")
    _mime, back = split_data_uri(uri)
    assert back == raw


def test_data_uri_within_budget_is_untouched():
    """已在预算内 -> 原样返回且不产生报告, 绝不做无谓重编码。"""
    raw = _noisy_png(64, 64)
    uri = build_data_uri(raw, "image/png")
    out, res = compress_data_uri_to_wire_budget(uri, 10 * 1024 * 1024)
    assert out == uri and res is None


def test_data_uri_over_budget_is_compressed():
    raw = _noisy_png(1200, 900)
    uri = build_data_uri(raw, "image/png")
    wire_budget = 200 * 1024
    out, res = compress_data_uri_to_wire_budget(uri, wire_budget)
    assert res is not None and res.ok, res.summary() if res else "no result"
    assert len(out) <= wire_budget + 64, len(out)   # +64 容纳 "data:image/webp;base64," 头
    assert out.startswith("data:image/")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[FAIL] {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
