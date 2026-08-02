"""MiniMax / Anthropic 适配器真实联调 (走编排器真实代码路径, 非裸 curl).

用法 (容器内):
    python /app/verify_minimax_adapter.py

验证矩阵:
  1. 文本      MiniMax-M2        -> /v1/chat/completions
  2. Anthropic MiniMax-M2        -> /anthropic/v1/messages
  3. 图像      image-01          -> /v1/image_generation
  4. 视频 v2   MiniMax-H3        -> /v2/video_generation + 查询
  5. 视频 v1   MiniMax-Hailuo-02 -> /v1/video_generation + 查询
  6. 错误语义  故意用不存在的模型 -> 必须抛错(不能静默成功)
"""
from __future__ import annotations

import asyncio
import base64
import sys
import time
import traceback

KEY = ("sk-api-mELFQR0n6C3YXNK17vIh7V8SjSdrvwtuBvHXi0jHgLQvJBYvV2ECk4aU0FUOjHQGZXOS"
       "nXhD25QiiljSxDQj8rwAasiT3b_pOVb8L0JjPZsdUy649CAJVi0")
BASE = "https://api.minimaxi.com"

# 1x1 红点 PNG, 用于验证 data URI 内联参考图路径
PNG_1X1 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

from app.async_core.engine import get_loop  # noqa: E402
from app.async_core.provider_adapter import build_adapter  # noqa: E402

PASS, FAIL = [], []


def run(coro):
    """把协程提交到编排器真实事件循环 (与生产链路一致), 同步等结果。"""
    fut = asyncio.run_coroutine_threadsafe(coro, get_loop())
    return fut.result(timeout=600)


def adapter(model: str, ptype: str = "minimax", base: str = BASE):
    return build_adapter({
        "provider_type": ptype, "base_url": base, "api_key": KEY,
        "model_name": model, "provider_name": f"minimax-{model}",
    })


def case(name):
    def deco(fn):
        def wrapped():
            print(f"\n{'=' * 68}\n▶ {name}\n{'=' * 68}")
            t0 = time.time()
            try:
                fn()
                PASS.append(name)
                print(f"✅ PASS  ({time.time() - t0:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                FAIL.append((name, repr(exc)))
                print(f"❌ FAIL  ({time.time() - t0:.1f}s): {exc}")
                traceback.print_exc(limit=3)
        return wrapped
    return deco


@case("0. 模型路由表 (纯本地, 防前缀冲突回归)")
def t_routing():
    """联调事故复盘: 'minimax-h' 前缀同时吃掉了 Hailuo 系列, v1 模型被打到 v2 端点。

    此用例把每个模型该走哪条路线钉死, 未来加模型改前缀时能立刻发现串线。
    """
    expect = {
        # v2: H 系列 (字母 H 后接数字)
        "MiniMax-H3": "video_v2",
        # v1: Hailuo / T2V / I2V / S2V / video-01 系列
        "MiniMax-Hailuo-02": "video_v1",
        "MiniMax-Hailuo-2.3": "video_v1",
        "MiniMax-Hailuo-2.3-Fast": "video_v1",
        "T2V-01-Director": "video_v1",
        "I2V-01-live": "video_v1",
        "S2V-01": "video_v1",
        "video-01-live2d": "video_v1",
        # 其它族
        "image-01": "image",
        "image-01-live": "image",
        "MiniMax-M2": "text",
        "MiniMax-M2.7-highspeed": "text",
        "music-1.5": "music",
        "speech-2.5-hd-preview": "speech",
    }
    bad = []
    for model, want in expect.items():
        got = adapter(model)._kind({"type": "video"})
        flag = "ok" if got == want else "MISROUTED"
        if got != want:
            bad.append(f"{model}: 期望 {want}, 实际 {got}")
        print(f"   {model:28s} -> {got:9s} [{flag}]")
    assert not bad, "路由串线:\n     " + "\n     ".join(bad)


@case("1. 文本 MiniMax-M2 -> /v1/chat/completions")
def t_text():
    a = adapter("MiniMax-M2")
    out = run(a.submit({
        "type": "text", "job_id": "v-text", "user_id": 1,
        "prompt": "用一句话说明什么是防腐层(ACL)设计模式。",
        "params": {"max_tokens": 4096},
    }))
    assert out.sync, "文本必须同步返回"
    r = out.result
    assert r.text and len(r.text) > 5, f"文本为空: {r.text!r}"
    assert "<think>" not in r.text, "think 块未被剥离!"
    print(f"   text[:120] = {r.text[:120]!r}")
    print(f"   usage      = {r.usage}")
    assert r.usage.get("total_tokens", 0) > 0, "usage 未归一化"


@case("2. Anthropic 兼容 MiniMax-M2 -> /anthropic/v1/messages")
def t_anthropic():
    a = adapter("MiniMax-M2", ptype="anthropic-compatible", base=f"{BASE}/anthropic")
    out = run(a.submit({
        "type": "text", "job_id": "v-anthropic", "user_id": 1,
        "prompt": "只回答两个字: 收到",
        "params": {"max_tokens": 2048, "system": "你是简洁的助手"},
    }))
    r = out.result
    assert r.text, "Anthropic 返回空文本"
    print(f"   text[:120] = {r.text[:120]!r}")
    print(f"   usage      = {r.usage}")
    assert r.usage.get("input_tokens", 0) > 0, "input_tokens 未解析"


@case("2b. Anthropic 视觉输入 (data URI -> base64 source)")
def t_anthropic_vision():
    a = adapter("MiniMax-M2", ptype="anthropic-compatible", base=f"{BASE}/anthropic")
    payload = a._build_payload({
        "type": "text", "prompt": "这是什么颜色?",
        "params": {"reference_images": [PNG_1X1], "max_tokens": 1024},
    })
    blocks = payload["messages"][0]["content"]
    img = [b for b in blocks if b.get("type") == "image"]
    assert len(img) == 1, f"视觉块未生成: {blocks}"
    assert img[0]["source"]["type"] == "base64", "data URI 未转 base64 source"
    assert img[0]["source"]["media_type"] == "image/png"
    assert "data:" not in img[0]["source"]["data"], "data URI 前缀未剥离"
    print(f"   image block ok, media_type={img[0]['source']['media_type']}, "
          f"data_len={len(img[0]['source']['data'])}")
    # 真实打一次, 确认服务端接受
    out = run(a.submit({
        "type": "text", "job_id": "v-vision", "user_id": 1,
        "prompt": "简短描述这张图。",
        "params": {"reference_images": [PNG_1X1], "max_tokens": 4096},
    }))
    print(f"   server accepted, text[:80] = {out.result.text[:80]!r}")


@case("3. 图像 image-01 -> /v1/image_generation")
def t_image():
    a = adapter("image-01")
    out = run(a.submit({
        "type": "image", "job_id": "v-img", "user_id": 1,
        "prompt": "a serene mountain lake at dawn, cinematic",
        "params": {"aspectRatio": "16:9", "n": 1, "resolution": "2K"},
    }))
    assert out.sync, "图像必须同步返回"
    r = out.result
    assert r.url.startswith("http"), f"图像 URL 异常: {r.url!r}"
    print(f"   url   = {r.url[:110]}")
    print(f"   urls  = {len(r.urls)} 张")


@case("4. 视频 v2 MiniMax-H3 -> /v2/video_generation (提交+查询)")
def t_video_v2():
    a = adapter("MiniMax-H3")
    out = run(a.submit({
        "type": "video", "job_id": "v-v2", "user_id": 1,
        "prompt": "a paper boat drifting on a calm lake, slow motion",
        "params": {"duration": 6, "aspectRatio": "16:9", "resolution": "2K",
                   "reference_images": [PNG_1X1]},
    }))
    assert not out.sync, "视频必须异步返回句柄"
    h = out.handle
    assert h.provider_task_id, "未拿到 task_id"
    assert "/v2/query/" in h.status_query, f"状态查询地址错: {h.status_query}"
    print(f"   task_id      = {h.provider_task_id}")
    print(f"   status_query = {h.status_query}")
    st = a.query_status(h)
    print(f"   poll#1 -> normalized={st.normalized.value} raw={st.raw_status!r}")
    assert st.normalized.value in ("pending", "processing", "done"), \
        f"提交后立刻失败: {st.error}"


@case("5. 视频 v1 MiniMax-Hailuo-02 -> /v1/video_generation (提交+查询)")
def t_video_v1():
    a = adapter("MiniMax-Hailuo-02")
    out = run(a.submit({
        "type": "video", "job_id": "v-v1", "user_id": 1,
        "prompt": "close-up of morning dew on a green leaf",
        "params": {"duration": 6, "resolution": "1K"},
    }))
    assert not out.sync, "视频必须异步返回句柄"
    h = out.handle
    assert h.provider_task_id, "未拿到 task_id"
    assert "/v1/query/" in h.status_query, f"状态查询地址错: {h.status_query}"
    print(f"   task_id      = {h.provider_task_id}")
    print(f"   status_query = {h.status_query}")
    st = a.query_status(h)
    print(f"   poll#1 -> normalized={st.normalized.value} raw={st.raw_status!r}")
    assert st.normalized.value in ("pending", "processing", "done"), \
        f"提交后立刻失败: {st.error}"


@case("6. 错误语义: HTTP 200 + base_resp!=0 必须抛错 (v1 核心陷阱)")
def t_error_semantics():
    a = adapter("no-such-model-xyz")
    # model 名不匹配任何前缀 -> 回落到 req type=video -> v2 端点
    # 改为显式测 v1 图像端点的 base_resp 语义
    a2 = adapter("image-01")
    a2.model_name = "image-does-not-exist"
    raised = None
    try:
        run(a2._gen_image({
            "type": "image", "prompt": "test",
            "params": {"n": 1},
        }))
    except Exception as exc:  # noqa: BLE001
        raised = exc
    assert raised is not None, "❌ 严重: 不存在的模型竟然没抛错 (会导致扣费给空结果)"
    msg = str(raised)
    print(f"   正确抛出: {msg[:160]}")
    assert "base_resp" in msg or "HTTP" in msg, f"错误信息未体现真实原因: {msg}"


def main():
    for fn in (t_routing, t_text, t_anthropic, t_anthropic_vision, t_image,
               t_video_v2, t_video_v1, t_error_semantics):
        fn()
    print(f"\n{'#' * 68}")
    print(f"# 通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    for p in PASS:
        print(f"#   ✅ {p}")
    for n, e in FAIL:
        print(f"#   ❌ {n}\n#      {e[:200]}")
    print(f"{'#' * 68}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
