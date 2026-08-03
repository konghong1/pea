"""火山方舟 vendor-native 适配器：路由 + 字段构造验证（不花钱）。

验证目标：
1. build_adapter 多维路由：
   - (vendor-native, volcengine) -> VolcengineAdapter
   - (vendor-native, minimax)    -> MiniMaxAdapter（路由不被破坏）
   - (openai-compatible, None)    -> OpenAI 兼容适配器（路由不被破坏）
   - (vendor-native, unknown)     -> ValueError（未实现原生协议应明确报错）
2. 火山三条路径的请求体字段构造（仅构造，不发起真实 HTTP）。
"""
import os
import sys

# 让 app 包可导入
GO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "pea-server", "services", "generation-orchestrator")
)
sys.path.insert(0, GO_ROOT)

from app.async_core import provider_adapter as pa  # noqa: E402  (触发 app.providers 注册)


def route_name(cfg):
    return type(pa.build_adapter(cfg)).__name__


PASS = []
FAIL = []


def check(label, cond, detail=""):
    (PASS if cond else FAIL).append((label, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))


# ---- 1. 路由 ----
cfg_vol = {"protocol": "vendor-native", "vendor": "volcengine",
           "base_url": "https://ark.cn-beijing.volces.com/api/v3", "api_key": "x"}
check("route (vendor-native, volcengine) -> VolcengineAdapter",
      route_name(cfg_vol) == "VolcengineAdapter", route_name(cfg_vol))

cfg_mm = {"protocol": "vendor-native", "vendor": "minimax",
          "base_url": "https://api.minimax.chat", "api_key": "x"}
check("route (vendor-native, minimax) -> MiniMaxAdapter (unchanged)",
      route_name(cfg_mm) == "MiniMaxAdapter", route_name(cfg_mm))

cfg_oa = {"protocol": "openai-compatible", "vendor": None,
          "base_url": "https://api.openai.com/v1", "api_key": "x"}
name_oa = route_name(cfg_oa)
check("route (openai-compatible) -> OpenAI 兼容 (AgnesAdapter)",
      name_oa in ("AgnesAdapter",), name_oa)

try:
    pa.build_adapter({"protocol": "vendor-native", "vendor": "nope", "base_url": "x"})
    check("route (vendor-native, unknown) raises ValueError", False, "未抛错")
except ValueError:
    check("route (vendor-native, unknown) raises ValueError", True)
except Exception as e:  # noqa: BLE001
    check("route (vendor-native, unknown) raises ValueError", False, f"抛错类型不符: {type(e).__name__}")

# ---- 2. 请求体字段构造（不发起 HTTP） ----
from app.providers.volcengine import VolcengineAdapter  # noqa: E402

ad = VolcengineAdapter(cfg_vol)


def fake_req(**kw):
    r = {"type": "image", "prompt": "a cat", "model_name": "seedream-3.0", "n": 1,
         "refs": [], "size": "2K", "ratio": "1:1"}
    r.update(kw)
    return r


# 2a. 图像 payload
img_payload = ad._build_image_payload(fake_req(model_name="seedream-3.0", size="2K"))
check("image payload.model == seedream-3.0", img_payload.get("model") == "seedream-3.0", str(img_payload))
check("image payload.response_format == url", img_payload.get("response_format") == "url")
check("image payload.size 档位式 == 2K", img_payload.get("size") == "2K")
check("image payload.watermark == False", img_payload.get("watermark") is False)
check("image payload.prompt 存在", bool(img_payload.get("prompt")))

# 2b. 图生图（SeedEdit）：refs 内联进 image[]（base64 策略）
edit_payload = ad._build_image_payload(
    fake_req(model_name="seededit-3.0", refs=[{"kind": "image", "uri": "data:image/png;base64,AAAA"}])
)
check("seededit 走 image[] 内联 (len==1)", len(edit_payload.get("image", [])) == 1, str(edit_payload.get("image")))

# 2c. 视频 payload
vid_payload = ad._build_video_payload(
    fake_req(type="video", model_name="seedance-1.0-lite", duration=10,
             refs=[{"kind": "image", "uri": "https://x/y.png"}])
)
content = vid_payload.get("content", [])
check("video payload.model == seedance-1.0-lite", vid_payload.get("model") == "seedance-1.0-lite")
check("video content 含 text 段", any(c.get("type") == "text" for c in content))
check("video content 含 image_url 段 (首张参考图)", any(c.get("type") == "image_url" for c in content))
check("video resolution 由 tier 映射", vid_payload.get("resolution") in ("480p", "720p", "1080p"),
      str(vid_payload.get("resolution")))
check("video generate_audio == True", vid_payload.get("generate_audio") is True)

# 2d. URL 前缀处理（关键坑）
u_img = ad._url("/images/generations")
u_vid = ad._url("/contents/generations/tasks")
check("image endpoint 无双 /api/v3 前缀",
      u_img == "https://ark.cn-beijing.volces.com/api/v3/images/generations", u_img)
check("video endpoint 无双 /api/v3 前缀",
      u_vid == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks", u_vid)

# 2e. _kind 路由
check("_kind image (seedream)", ad._kind(fake_req(model_name="seedream-x")) == "image")
check("_kind video (seedance)", ad._kind(fake_req(model_name="seedance-x")) == "video")
check("_kind text (doubao)", ad._kind(fake_req(type="text", model_name="doubao-seed-1.6")) == "text")

print("\n==== SUMMARY ====")
print(f"PASS={len(PASS)} FAIL={len(FAIL)}")
if FAIL:
    print("FAILURES:")
    for label, detail in FAIL:
        print(f"  - {label} :: {detail}")
    sys.exit(1)
print("ALL_PASS")
