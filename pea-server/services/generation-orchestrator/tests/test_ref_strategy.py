"""
参考图解析策略单测 (在编排器容器内运行, 依赖 app 包与 minio 等依赖已就绪)。

验证:
- Base64InlineStrategy (图片): data:/公网URL 原样保留; 内网/相对 URL 经 MinIO 转 base64。
- PublicUrlStrategy (视频): 把 data:/内部 URL 转存为外部模型可下载的公网 URL。
- 各 ImageParamAdapter 默认声明 Base64InlineStrategy (不经公网)。
"""
import sys

sys.path.insert(0, "/app")

from unittest import mock

from app.param_adapters import (
    AgnesImageAdapter,
    Base64InlineStrategy,
    GenericOpenAIImageAdapter,
    PublicUrlStrategy,
    _normalize_refs,
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
