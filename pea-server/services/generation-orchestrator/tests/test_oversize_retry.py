"""「参考图过大」自愈重试单测 (provider 层被动防线)。

验证四条不变量:
  1. 上游明确回「图太大」+ 有参考图 -> 压缩后重试一次, 且第二次请求体里的图确实变小了;
  2. 无关错误 (限流/鉴权/内容策略) 绝不触发重试 —— 否则白烧额度还掩盖真实原因;
  3. 压缩后仍失败 -> 只重试一次就把真实错误抛出去, 不无限重试;
  4. 开关 PEA_REF_OVERSIZE_AUTO_COMPRESS=false 时整条自愈关闭。

运行: docker exec <orchestrator> python /app/tests/test_oversize_retry.py
"""
import base64
import os
import sys
from io import BytesIO

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ★ 必须先加载 async_core 包: agnes_provider 与 async_core.provider_adapter 互相引用,
#   直接先导 agnes_provider 会撞上部分初始化的循环导入 (线上由 main.py 先导 async_core,
#   故不影响运行时; 这里显式对齐同样的加载顺序)。
import app.async_core  # noqa: E402,F401
import app.agnes_provider as ap  # noqa: E402
from app.agnes_provider import (  # noqa: E402
    OpenAICompatibleProvider,
    _compress_refs_for_retry,
    _should_retry_oversize,
)
from app.config import settings  # noqa: E402
from app.image_compress import split_data_uri, wire_len  # noqa: E402


class FakeResp:
    """最小 requests/httpx Response 替身 (只需要 status_code / text / json)。"""

    def __init__(self, status_code: int, text: str = "", payload: dict | None = None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}
        self.reason = "fake"

    def json(self):
        return self._payload


def _big_data_uri(w=1600, h=1200) -> str:
    from PIL import Image

    img = Image.frombytes("RGB", (w, h), os.urandom(w * h * 3))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider({
        "base_url": "https://apihub.agnes-ai.com/v1",
        "api_key": "sk-test",
        "model_name": "agnes-image-v2.0",
        "provider_name": "agnes-test",
    })


# ── 1. 触发判定 ──────────────────────────────────────────────────────────────
def test_should_retry_on_oversize_body():
    assert _should_retry_oversize(FakeResp(400, "图片超过10m"), has_refs=True)
    assert _should_retry_oversize(FakeResp(413, ""), has_refs=True)
    assert _should_retry_oversize(FakeResp(400, "image too large"), has_refs=True)


def test_should_not_retry_without_refs():
    """文生图没有参考图, 大小类错误也不可能是参考图造成的。"""
    assert not _should_retry_oversize(FakeResp(400, "图片超过10m"), has_refs=False)


def test_should_not_retry_on_unrelated_errors():
    for body in ("rate limit exceeded", "invalid api key", "content policy violation"):
        assert not _should_retry_oversize(FakeResp(400, body), has_refs=True), body
    assert not _should_retry_oversize(FakeResp(200, "ok"), has_refs=True)


def test_switch_off_disables_retry():
    old = settings.ref_oversize_auto_compress
    settings.ref_oversize_auto_compress = False
    try:
        assert not _should_retry_oversize(FakeResp(413, ""), has_refs=True)
    finally:
        settings.ref_oversize_auto_compress = old


# ── 2. 压缩本身 ──────────────────────────────────────────────────────────────
def test_compress_refs_shrinks_inline_ref():
    uri = _big_data_uri()
    budget = 300 * 1024
    out, n = _compress_refs_for_retry([uri], budget)
    assert n == 1
    _mime, raw = split_data_uri(out[0])
    assert wire_len(len(raw)) <= budget, wire_len(len(raw))


def test_compress_refs_is_fail_open():
    """不是图片 / 拉不动的 URL -> 保留原值, 绝不因压缩失败让任务挂掉。"""
    junk = "data:image/png;base64," + base64.b64encode(b"not-an-image" * 100).decode()
    out, n = _compress_refs_for_retry([junk], 1024)
    assert out == [junk] and n == 0


def test_compress_refs_skips_small_ones():
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (32, 32), (1, 2, 3)).save(buf, format="PNG")
    small = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    out, n = _compress_refs_for_retry([small], 6 * 1024 * 1024)
    assert out == [small] and n == 0, "已在预算内的图不该被重编码"


# ── 3. 端到端: 第一次 413 -> 压缩 -> 第二次成功 ───────────────────────────────
def test_generate_image_retries_with_compressed_ref():
    calls: list[dict] = []

    def fake_post(url, payload, headers, timeout, **kw):
        calls.append(payload)
        if len(calls) == 1:
            return FakeResp(400, '{"error":"图片超过10m"}')
        return FakeResp(200, "", {"data": [{"url": "https://cdn/x.png"}]})

    orig = ap._post_with_retry
    ap._post_with_retry = fake_post
    try:
        res = _provider()._generate_image({
            "type": "image",
            "prompt": "a cat",
            "params": {"reference_images": [_big_data_uri()], "size": "2K"},
        })
    finally:
        ap._post_with_retry = orig

    assert res.url == "https://cdn/x.png", res
    assert len(calls) == 2, f"应恰好重试一次, 实际 {len(calls)} 次"
    first = calls[0]["extra_body"]["image"][0]
    second = calls[1]["extra_body"]["image"][0]
    assert len(second) < len(first), "重试用的图必须比第一次小"
    assert wire_len(len(split_data_uri(second)[1])) <= settings.ref_oversize_retry_wire_bytes


def test_generate_image_no_retry_on_other_error():
    calls: list[dict] = []

    def fake_post(url, payload, headers, timeout, **kw):
        calls.append(payload)
        return FakeResp(401, "invalid api key")

    orig = ap._post_with_retry
    ap._post_with_retry = fake_post
    try:
        _provider()._generate_image({
            "type": "image",
            "prompt": "a cat",
            "params": {"reference_images": [_big_data_uri()]},
        })
        raise AssertionError("应抛出上游 401")
    except RuntimeError as e:
        assert "401" in str(e), e
    finally:
        ap._post_with_retry = orig
    assert len(calls) == 1, "无关错误不得重试"


def test_generate_image_retries_only_once():
    calls: list[dict] = []

    def fake_post(url, payload, headers, timeout, **kw):
        calls.append(payload)
        return FakeResp(413, "payload too large")

    orig = ap._post_with_retry
    ap._post_with_retry = fake_post
    try:
        _provider()._generate_image({
            "type": "image",
            "prompt": "a cat",
            "params": {"reference_images": [_big_data_uri()]},
        })
        raise AssertionError("压缩后仍失败, 应抛出真实错误")
    except RuntimeError as e:
        assert "413" in str(e), e
    finally:
        ap._post_with_retry = orig
    assert len(calls) == 2, f"最多重试一次, 实际 {len(calls)} 次"


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
