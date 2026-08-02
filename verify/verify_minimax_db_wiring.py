"""MiniMax 接入端到端闭环验证 (DB 配置 -> 适配器工厂 -> 真实上游调用)。

与 verify_minimax_adapter.py 的区别: 那个脚本手工构造 cfg 直接测适配器,
本脚本**从数据库真实读取** ai_models/ai_providers 配置, 走 dispatcher 用的
同一条 load_model_provider_cfg -> build_adapter 路径, 验证"管理后台配好就能用"。

重点回归项:
  ① 每个 seed 的模型都能解析出正确的适配器类 (provider_type 拼错会静默回退)
  ② 纯文生视频 (无参考图) 必须带 ratio —— 修复前 100% 打 400
  ③ 分辨率钳制不能把 Hailuo 的 2K 诉求降成 512P
"""
from __future__ import annotations

import asyncio
import sys
import traceback

sys.path.insert(0, "/app")

from app.async_core.db_async import load_model_provider_cfg  # noqa: E402
from app.async_core.engine import ensure_started, get_loop  # noqa: E402
from app.async_core.provider_adapter import build_adapter  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str) -> None:
    PASS.append(name)
    print(f"  \033[32mPASS\033[0m {name}")


def bad(name: str, err: object) -> None:
    FAIL.append(name)
    print(f"  \033[31mFAIL\033[0m {name}: {err}")


def run(coro):
    return asyncio.run_coroutine_threadsafe(coro, get_loop()).result(timeout=180)


# ── ① 适配器解析 ────────────────────────────────────────────────
EXPECTED = {
    "minimax-h3": ("minimax", "MiniMaxAdapter", "MiniMax-H3"),
    "minimax-hailuo-02": ("minimax", "MiniMaxAdapter", "MiniMax-Hailuo-02"),
    "minimax-image-01": ("minimax", "MiniMaxAdapter", "image-01"),
    "minimax-m2": ("minimax", "MiniMaxAdapter", "MiniMax-M2"),
    "minimax-m2-5": ("minimax", "MiniMaxAdapter", "MiniMax-M2.5"),
    "minimax-anthropic-m2": ("anthropic-compatible", "AnthropicCompatAdapter", "MiniMax-M2"),
}


def check_wiring() -> dict[str, object]:
    print("\n[1] DB 配置 -> 适配器工厂")
    adapters: dict[str, object] = {}
    for model_id, (ptype, cls_name, model_name) in EXPECTED.items():
        try:
            cfg = load_model_provider_cfg(model_id)
            assert cfg is not None, "load_model_provider_cfg 返回 None (模型未 seed?)"
            assert cfg["provider_type"] == ptype, f"provider_type={cfg['provider_type']} != {ptype}"
            assert cfg["model_name"] == model_name, f"model_name={cfg['model_name']} != {model_name}"
            a = build_adapter(cfg)
            got = type(a).__name__
            assert got == cls_name, f"适配器={got} != {cls_name} (工厂回退了!)"
            adapters[model_id] = a
            ok(f"{model_id} -> {got}({model_name})")
        except Exception as e:  # noqa: BLE001
            bad(f"{model_id} 适配器解析", e)
    return adapters


# ── ② 纯文生视频必须带 ratio (核心回归) ────────────────────────
def check_t2v_ratio(adapters: dict) -> None:
    print("\n[2] 纯文生视频 ratio 必填 (修复前 100% 打 400)")
    a = adapters.get("minimax-h3")
    if a is None:
        bad("H3 t2v ratio", "适配器缺失, 跳过")
        return
    try:
        # 前端完全没给 aspectRatio 的最朴素场景
        p = a._build_v2_payload({"prompt": "a cat walking on the beach", "params": {}})
        assert "ratio" in p, "纯文本场景没有下发 ratio -> 上游必然 400"
        assert p["ratio"] == "16:9", f"默认 ratio={p['ratio']} 应为 16:9"
        assert p["resolution"] == "2K", f"H3 resolution={p['resolution']} 应钳制为 2K"
        ok(f"t2v 无 aspectRatio -> 自动补 ratio={p['ratio']} resolution={p['resolution']}")

        # 前端给了 H3 不支持的 3:2 (通用白名单里有, t2v 白名单里没有)
        p2 = a._build_v2_payload({"prompt": "x", "params": {"aspectRatio": "3:2"}})
        assert p2["ratio"] == "16:9", f"非法 t2v ratio 未回退, 得到 {p2['ratio']}"
        ok("t2v 非法 ratio=3:2 -> 回退 16:9")

        # 图生视频: 有首帧时不应强塞 ratio (否则裁剪用户的图)
        tiny = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        p3 = a._build_v2_payload({"prompt": "x", "params": {"reference_images": [tiny]}})
        assert any(c.get("type") == "image_url" for c in p3["content"]), "首帧未进 content"
        assert "ratio" not in p3, "图生视频不应强制 ratio (应跟随首帧尺寸)"
        ok("i2v 有首帧 -> 不强塞 ratio, 跟随首帧")
    except Exception as e:  # noqa: BLE001
        bad("H3 t2v ratio", e)


# ── ③ 分辨率就近钳制 ────────────────────────────────────────────
def check_resolution_clamp() -> None:
    print("\n[3] 分辨率就近钳制 (不能把高画质诉求降到最低档)")
    from app.providers.minimax import _clamp_resolution
    cases = [
        ("MiniMax-H3", "1080P", "2K", "H3 只有 2K, 任何诉求都归到 2K"),
        ("MiniMax-Hailuo-02", "2K", "1080P", "Hailuo 无 2K -> 就近降到 1080P 而非 512P"),
        ("MiniMax-Hailuo-02", "768P", "768P", "命中直接返回"),
        ("video-01", "1080P", "1080P", "未列白名单的模型不钳制"),
    ]
    for model, want, expect, why in cases:
        try:
            got = _clamp_resolution(model, want)
            assert got == expect, f"{model} {want} -> {got}, 期望 {expect}"
            ok(f"{model}: {want} -> {got}  ({why})")
        except Exception as e:  # noqa: BLE001
            bad(f"clamp {model} {want}", e)


# ── ④ 真实上游调用 (用 DB 配置直连) ─────────────────────────────
def check_live(adapters: dict) -> None:
    print("\n[4] 真实上游调用 (DB 配置直连)")

    a = adapters.get("minimax-image-01")
    if a:
        try:
            r = run(a.submit({"type": "image", "prompt": "a red apple on white table",
                              "params": {"n": 1, "size": "1K"}}))
            url = r.result.url or (r.result.urls or [None])[0]
            assert url, "图像未返回 URL"
            ok(f"image-01 出图 -> {url[:70]}...")
        except Exception as e:  # noqa: BLE001
            bad("image-01 真实出图", e)

    a = adapters.get("minimax-h3")
    if a:
        try:
            # 关键: params 完全为空, 模拟"用户只填了提示词"
            r = run(a.submit({"type": "video", "job_id": "verify-t2v",
                              "prompt": "a paper boat drifting down a rainy street",
                              "params": {}}))
            assert not r.sync and r.handle.provider_task_id, "未拿到异步句柄"
            ok(f"H3 纯文生视频提交成功 task_id={r.handle.provider_task_id}")
        except Exception as e:  # noqa: BLE001
            bad("H3 纯文生视频提交", e)

    a = adapters.get("minimax-anthropic-m2")
    if a:
        try:
            r = run(a.submit({"type": "text", "prompt": "只回复两个字: 收到",
                              "params": {"max_tokens": 2048}}))
            txt = (r.result.text or "").strip()
            assert txt, "Anthropic 协议返回空正文"
            ok(f"Anthropic 协议文本 -> {txt[:40]!r}")
        except Exception as e:  # noqa: BLE001
            bad("Anthropic 协议文本", e)


def main() -> int:
    ensure_started()
    adapters = check_wiring()
    check_t2v_ratio(adapters)
    check_resolution_clamp()
    check_live(adapters)
    total = len(PASS) + len(FAIL)
    print(f"\n{'=' * 62}\n通过 {len(PASS)} / {total}")
    for f in FAIL:
        print(f"  \033[31m×\033[0m {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
