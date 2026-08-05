"""
参考图解析策略单测 (在编排器容器内运行, 依赖 app 包与 minio 等依赖已就绪)。

验证:
- Base64InlineStrategy (图片): data:/公网URL 原样保留; 内网/相对 URL 经 MinIO 转 base64。
- PublicUrlStrategy (视频): 把 data:/内部 URL 转存为外部模型可下载的公网 URL。
- 各 ImageParamAdapter 默认声明 Base64InlineStrategy (不经公网)。
"""
import base64
import sys

sys.path.insert(0, "/app")

from unittest import mock

from app.param_adapters import (
    AGNES_REF_BUDGET,
    UNLIMITED_REF_BUDGET,
    AgnesImageAdapter,
    Base64InlineStrategy,
    FixedRefBudget,
    GenericOpenAIImageAdapter,
    PublicUrlStrategy,
    RefImageBudget,
    UnlimitedRefBudget,
    _normalize_refs,
    get_ref_budget,
    register_ref_budget,
)


FAKE_B64 = "data:image/png;base64,FAKEB64DATA"


def test_base64_inline_keeps_data_uri_and_public_url():
    s = Base64InlineStrategy()
    refs = ["data:image/png;base64,AAAA", "https://cdn.example.com/a.png"]
    out = s.resolve(refs, provider=None)
    assert out == refs, out


def test_base64_inline_internal_url_becomes_base64():
    import app.param_adapters as pa

    with mock.patch.object(pa, "_resolve_internal_ref_via_minio", return_value=FAKE_B64):
        s = Base64InlineStrategy()
        out = s.resolve(["http://localhost:9000/pea-media/u:1/x.png"], provider=None)
    assert out == [FAKE_B64], out


def test_base64_inline_relative_media_path_becomes_base64():
    import app.param_adapters as pa

    with mock.patch.object(pa, "_resolve_internal_ref_key", return_value=FAKE_B64):
        s = Base64InlineStrategy()
        out = s.resolve(["/media/gen/images/1/2026/07/30/eaa.png"], provider=None)
    assert out == [FAKE_B64], out


def test_base64_inline_drops_blob_and_unreachable():
    import app.param_adapters as pa

    with mock.patch.object(pa, "_resolve_internal_ref_via_minio", return_value=None):
        s = Base64InlineStrategy()
        out = s.resolve(
            ["blob:http://localhost/x", "http://localhost:9000/pea-media/missing.png"],
            provider=None,
        )
    assert out == [], out


def test_public_url_strategy_converts_via_provider():
    class FakeProvider:
        def resolve_refs(self, refs):
            return [
                r.replace("data:", "https://cdn.example.com/gen/")
                if r.startswith("data:")
                else r
                for r in refs
            ]

    s = PublicUrlStrategy()
    out = s.resolve(["data:image/png;base64,ZZZ"], provider=FakeProvider())
    assert out == ["https://cdn.example.com/gen/image/png;base64,ZZZ"], out


def test_public_url_strategy_requires_provider():
    s = PublicUrlStrategy()
    try:
        s.resolve(["data:image/png;base64,ZZZ"], provider=None)
        assert False, "should have raised (provider required)"
    except RuntimeError:
        pass


def test_adapters_declare_inline_strategy():
    assert isinstance(AgnesImageAdapter().ref_strategy, Base64InlineStrategy)
    assert isinstance(GenericOpenAIImageAdapter().ref_strategy, Base64InlineStrategy)


def test_normalize_image_params_stores_raw_refs():
    from app.param_adapters import normalize_image_params

    norm = normalize_image_params(
        {"prompt": "x", "params": {"reference_images": ["/media/a.png", "https://c/b.png"]}}
    )
    # 仅做基础规整, 不做 base64 转换 (转换交由策略在 provider 层执行)
    assert norm.reference_images == ["/media/a.png", "https://c/b.png"], norm.reference_images


def test_base64_inline_over_threshold_url_fallback():
    """超阈值 + 降采样不可用 -> 走连接兜底（上传公开存储返回公网 URL）。"""
    import app.param_adapters as pa

    class FakeProvider:
        def resolve_refs(self, refs):
            return ["https://cdn.example.com/gen/fallback.png"]

    # "AAAA" -> 3 字节原图, 线上 4 字节; 预算 inline = 4-1 = 3 -> 必超阈值
    tiny = FixedRefBudget("tiny", upstream_limit_bytes=4, headroom_bytes=1)
    with mock.patch.object(pa, "_downsample_image_bytes", side_effect=ImportError("no PIL")):
        s = Base64InlineStrategy(tiny)
        out = s.resolve(["data:image/png;base64,AAAA"], provider=FakeProvider())
    assert out == ["https://cdn.example.com/gen/fallback.png"], out


def test_base64_inline_over_threshold_downsamples_inline():
    """超阈值 + 有 Pillow -> 降采样后仍以 data: 内联（保隐私, 线上字节 ≤ 预算）。"""
    import app.param_adapters as pa

    try:
        from PIL import Image
        from io import BytesIO
    except ImportError:
        return  # 无 Pillow 环境跳过（容器已装 Pillow 时生效）

    buf = BytesIO()
    Image.new("RGB", (4000, 4000), (255, 255, 255)).save(buf, format="PNG")
    big = buf.getvalue()
    data_uri = "data:image/png;base64," + base64.b64encode(big).decode()
    budget = FixedRefBudget("small", upstream_limit_bytes=64 * 1024, headroom_bytes=8 * 1024)
    assert not budget.accepts_inline(len(big)), "用例前提: 原图应超预算"
    s = Base64InlineStrategy(budget)
    # 无 provider -> 不能 URL 兜底, 只能内联降采样
    out = s.resolve([data_uri], provider=None)
    assert out and out[0].startswith("data:"), out
    _m, b = pa._split_data_uri(out[0])
    assert budget.accepts_inline(len(base64.b64decode(b))), "应降采样到预算内"


# ── 参考图预算适配层 (RefImageBudget) ────────────────────────────────────────
def test_default_strategy_is_unlimited():
    """默认策略不设限: 超大图原样内联, 不降采样、不改一个字节。"""
    huge = "data:image/png;base64," + "A" * (12 * 1024 * 1024)
    s = Base64InlineStrategy()
    assert isinstance(s.budget, UnlimitedRefBudget), s.budget
    assert s.resolve([huge], provider=None) == [huge], "无上限时必须原样透传"


def test_unlimited_budget_contract():
    b = UNLIMITED_REF_BUDGET
    assert b.inline_wire_limit() is None
    assert b.source_bytes_limit() is None
    assert b.enforced is False
    assert b.downsample_target_bytes() is None
    assert b.accepts_inline(999 * 1024 * 1024) and b.accepts_source(999 * 1024 * 1024)


def test_agnes_budget_contract():
    """Agnes 10MB 预算的契约（**已接线**）: 内联按线上字节留 1MB headroom -> 9MB。

    锁住 FixedRefBudget 的换算语义 —— base64 膨胀必须计入, 否则又会像初版那样
    「按解码字节卡 8MB, 实际线上 10.67MB」打穿上限。
    """
    b = AGNES_REF_BUDGET
    assert b.enforced is True
    assert b.inline_wire_limit() == 9 * 1024 * 1024
    assert b.source_bytes_limit() == 10 * 1024 * 1024
    assert b.downsample_target_bytes() == int(9 * 1024 * 1024 * 3 / 4)
    # 回归护栏: 7.7MB 原图 base64 后 10.27MB, 旧实现按解码字节会误放行
    assert not b.accepts_inline(int(7.7 * 1024 * 1024)), "base64 膨胀必须计入"
    assert b.accepts_inline(6 * 1024 * 1024)
    # URL 投递不经 base64 膨胀, 按原始字节判
    assert b.accepts_source(int(9.5 * 1024 * 1024))
    assert not b.accepts_source(int(10.5 * 1024 * 1024))


def test_fixed_budget_rejects_bad_headroom():
    for bad in (1024, 2048):
        try:
            FixedRefBudget("bad", upstream_limit_bytes=1024, headroom_bytes=bad)
            assert False, "headroom >= upstream 应该抛 ValueError"
        except ValueError:
            pass


def test_fixed_budget_source_opt_out():
    """某些家只限制请求体大小 -> applies_to_source=False 时 URL 投递不受限。"""
    b = FixedRefBudget("inline-only", upstream_limit_bytes=4 * 1024 * 1024,
                       applies_to_source=False)
    assert b.source_bytes_limit() is None
    assert b.accepts_source(100 * 1024 * 1024)
    assert b.inline_wire_limit() == 3 * 1024 * 1024


def test_strategy_rejects_non_budget():
    try:
        Base64InlineStrategy(budget=9 * 1024 * 1024)  # type: ignore[arg-type]
        assert False, "应拒绝非 RefImageBudget 实现"
    except TypeError:
        pass


def test_only_agnes_declares_limit():
    """★ 核心断言: 只有 Agnes 启用字节护栏; 其余提供商一律交上游判定, 不替它们猜规矩。"""
    assert AgnesImageAdapter().ref_strategy.budget.enforced is True, \
        "Agnes 已确认存在 10MB 级限制, 应启用护栏"
    assert GenericOpenAIImageAdapter().ref_strategy.budget.enforced is False, \
        "未证实有硬限的提供商不应被误伤降画质"


def test_env_budget_factory():
    """env 配置的边界收敛: 0 = 关闭; headroom 配错自动收敛而不是让服务起不来。"""
    from app.param_adapters import make_env_ref_budget

    assert make_env_ref_budget("off", 0, 1024) is UNLIMITED_REF_BUDGET
    assert make_env_ref_budget("neg", -1, 1024) is UNLIMITED_REF_BUDGET

    b = make_env_ref_budget("bad-headroom", 1000, 5000)   # headroom >= limit
    assert b.enforced is True
    assert 0 < b.inline_wire_limit() < 1000, b

    ok = make_env_ref_budget("ok", 10 * 1024 * 1024, 1024 * 1024)
    assert ok.inline_wire_limit() == 9 * 1024 * 1024
    assert ok.source_bytes_limit() == 10 * 1024 * 1024


def test_budget_registry():
    assert get_ref_budget("agnes") is AGNES_REF_BUDGET, "Agnes 已登记 10MB 预算"
    assert get_ref_budget("gemini") is UNLIMITED_REF_BUDGET, "未注册者不限"
    assert get_ref_budget(None) is UNLIMITED_REF_BUDGET

    # 注册表大小写不敏感; 新提供商实测确认有硬限时一行登记即可。
    register_ref_budget("Case-Test", AGNES_REF_BUDGET)
    assert get_ref_budget("case-test") is AGNES_REF_BUDGET
    assert get_ref_budget("CASE-TEST") is AGNES_REF_BUDGET, "key 应大小写不敏感"

    custom = FixedRefBudget("demo", upstream_limit_bytes=5 * 1024 * 1024)
    register_ref_budget("demo-provider", custom)
    assert get_ref_budget("demo-provider") is custom
    try:
        register_ref_budget("nope", object())  # type: ignore[arg-type]
        assert False, "应拒绝非 RefImageBudget 实现"
    except TypeError:
        pass


def test_budget_is_an_interface():
    """RefImageBudget 是抽象接口: 不实现全部抽象方法不能实例化。"""
    try:
        RefImageBudget()  # type: ignore[abstract]
        assert False, "抽象接口不应可直接实例化"
    except TypeError:
        pass

    class Partial(RefImageBudget):
        def inline_wire_limit(self):
            return 1

    try:
        Partial()  # type: ignore[abstract]
        assert False, "缺少 source_bytes_limit 实现不应可实例化"
    except TypeError:
        pass


if __name__ == "__main__":
    tests = [
        test_base64_inline_keeps_data_uri_and_public_url,
        test_base64_inline_internal_url_becomes_base64,
        test_base64_inline_relative_media_path_becomes_base64,
        test_base64_inline_drops_blob_and_unreachable,
        test_public_url_strategy_converts_via_provider,
        test_public_url_strategy_requires_provider,
        test_adapters_declare_inline_strategy,
        test_normalize_image_params_stores_raw_refs,
        test_base64_inline_over_threshold_url_fallback,
        test_base64_inline_over_threshold_downsamples_inline,
        test_default_strategy_is_unlimited,
        test_unlimited_budget_contract,
        test_agnes_budget_contract,
        test_fixed_budget_rejects_bad_headroom,
        test_fixed_budget_source_opt_out,
        test_strategy_rejects_non_budget,
        test_only_agnes_declares_limit,
        test_env_budget_factory,
        test_budget_registry,
        test_budget_is_an_interface,
    ]
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
