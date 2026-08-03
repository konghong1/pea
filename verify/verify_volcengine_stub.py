# -*- coding: utf-8 -*-
"""火山方舟适配器：隔离桩验证（不装 minio/sqlalchemy，不花钱）。

做法：用轻量桩替换 volcengine.py 的真实依赖（app.* / httpx / requests），
直接 importlib.exec_module 跑真实的 volcengine.py 代码，从而验证：
  1. @register_provider 注册键 == ("vendor-native","volcengine")
  2. 图像 payload 字段（size 档位式 / response_format=url / watermark=False / image[] 内联）
  3. 视频 payload 字段（content 含 text + 首张 image_url / resolution 映射 / ratio 白名单 / generate_audio）
  4. _url 前缀处理（无双 /api/v3）
  5. _kind 路由（seedream→image / seedance→video / doubao→text）
  6. 余额不足(402)错误分类 → 友好"余额不足"
"""
import importlib.util
import os
import sys
import types

PASS, FAIL = [], []


def check(label, cond, detail=""):
    (PASS if cond else FAIL).append((label, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))


# ── 桩：app 包及子模块 ─────────────────────────────────────────────
def mod(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


app = mod("app")
app.__path__ = []  # 使其成为 package，允许 from app.x import
app_agnes = mod("app.agnes_provider")
app_async = mod("app.async_core")
app_async.__path__ = []
app_types = mod("app.async_core.types")
app_pa = mod("app.async_core.provider_adapter")
app_cfg = mod("app.config")
app_param = mod("app.param_adapters")
mod("httpx")
mod("requests")

# app.agnes_provider 桩
app_agnes._short = lambda s: (s or "")[:80]
app_agnes._apost_with_retry = lambda *a, **k: None

# app.async_core.types 桩
import abc
from dataclasses import dataclass, field
from typing import Any


class _Enum:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


app_types.CompletionMode = _Enum(POLL="poll", SYNC="sync")
app_types.NormalizedStatus = _Enum(DONE="done", FAILED="failed", PROCESSING="processing", PENDING="pending")


@dataclass
class _AsyncHandle:
    job_id: str = ""
    user_id: int = 0
    provider: str = ""
    completion_mode: str = ""
    provider_task_id: str = ""
    status_query: str = ""


app_types.AsyncHandle = _AsyncHandle


@dataclass
class _GenResult:
    url: str = ""
    urls: list = field(default_factory=list)
    provider: str = ""
    raw: dict = field(default_factory=dict)
    text: str = ""
    usage: dict = field(default_factory=dict)


app_types.GenerationResult = _GenResult


@dataclass
class _PollStatus:
    normalized: str = ""
    raw_status: str = ""
    result_url: str = ""
    error: str = ""
    progress=None


app_types.PollStatus = _PollStatus


@dataclass
class _ProviderCaps:
    completion_mode: str = ""
    accepts_callback: bool = False


app_types.ProviderCapabilities = _ProviderCaps


@dataclass
class _SubmitOutcome:
    sync: bool = True
    result=None
    handle=None


app_types.SubmitOutcome = _SubmitOutcome

# app.async_core.provider_adapter 桩（注册表 + 基类）
app_pa = mod("app.async_core.provider_adapter")
app_pa.PROVIDER_REGISTRY = {}


def register_provider(protocol, vendor=None):
    def deco(cls):
        app_pa.PROVIDER_REGISTRY[(protocol, vendor)] = cls
        cls._reg_key = (protocol, vendor)
        return cls
    return deco


app_pa.register_provider = register_provider


class BaseProviderAdapter(abc.ABC):
    def __init__(self, cfg):
        self.base_url = cfg.get("base_url", "")
        self.api_key = cfg.get("api_key", "")
        self.model_name = cfg.get("model_name", "")
        self.provider_name = cfg.get("provider_name") or cfg.get("provider_id") or "provider"
        self.name = self.provider_name


app_pa.BaseProviderAdapter = BaseProviderAdapter

# app.config 桩
app_cfg.settings = types.SimpleNamespace(
    provider_image_timeout_s=120, provider_http_connect_timeout_s=10,
    provider_image_retry_attempts=2, provider_video_submit_timeout_s=120,
)

# app.param_adapters 桩（忠实复刻 normalize_image_params 的抽取逻辑）
@dataclass
class _Norm:
    prompt: str
    n: int = 1
    size_tier: str = None
    aspect_ratio: str = None
    seed: Any = None
    reference_images: list = field(default_factory=list)


def _clean_ref_list(refs):
    if not refs:
        return []
    if isinstance(refs, str):
        refs = [refs]
    out = []
    for r in refs:
        if isinstance(r, str) and r.strip():
            out.append(r.strip())
    return out[:8]


def normalize_image_params(req):
    p = req.get("params") or {}
    tier_raw = (p.get("resolution") or p.get("size") or "")
    tier = tier_raw.upper() if tier_raw else None
    try:
        n = int(p.get("n", 1))
    except (TypeError, ValueError):
        n = 1
    return _Norm(
        prompt=req["prompt"],
        n=max(1, min(8, n)),
        size_tier=tier,
        aspect_ratio=p.get("aspectRatio"),
        seed=p.get("seed"),
        reference_images=_clean_ref_list(p.get("reference_images")),
    )


app_param.normalize_image_params = normalize_image_params


class Base64InlineStrategy:
    def resolve(self, refs, provider=None):
        # 桩：data URI / 公网 URL 原样返回（仅做结构验证）
        return list(refs or [])


app_param.Base64InlineStrategy = Base64InlineStrategy

# ── 加载真实 volcengine.py（importlib.exec_module，依赖解析到上面的桩） ──
REAL = r"D:/workspace/pea/pea-server/services/generation-orchestrator/app/providers/volcengine.py"
spec = importlib.util.spec_from_file_location("volcengine_stubtest", REAL)
ve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ve)

VolcengineAdapter = ve.VolcengineAdapter

# ── 1. 注册键 ──
key = app_pa.PROVIDER_REGISTRY.get(("vendor-native", "volcengine"))
check("register key (vendor-native, volcengine) -> VolcengineAdapter",
      key is VolcengineAdapter, str(key))
check("未污染通用 (vendor-native, None) 槽位",
      ("vendor-native", None) not in app_pa.PROVIDER_REGISTRY)

# ── 构造适配器实例（适配器按模型绑定；_kind 回退与 payload.model 均读 self.model_name） ──
def mk(model_name):
    return VolcengineAdapter({
        "protocol": "vendor-native", "vendor": "volcengine",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key": "FAKE", "model_name": model_name, "provider_name": "volcengine",
    })


ad_img = mk("seedream-3.0")
ad_vid = mk("seedance-1.0-lite")
ad_txt = mk("doubao-seed-1.6")

# ── 2. _url 前缀 ──
check("image endpoint 无双 /api/v3",
      ad_img._url("/images/generations") == "https://ark.cn-beijing.volces.com/api/v3/images/generations",
      ad_img._url("/images/generations"))
check("video endpoint 无双 /api/v3",
      ad_vid._url("/contents/generations/tasks") == "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks",
      ad_vid._url("/contents/generations/tasks"))
# 兼容：base_url 不带 /api/v3 时也能拼对
ad2 = VolcengineAdapter({"base_url": "https://ark.cn-beijing.volces.com", "model_name": "x"})
check("base_url 无 /api/v3 尾时也拼对",
      ad2._url("/chat/completions") == "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
      ad2._url("/chat/completions"))

# ── 3. _kind 路由 ──
check("_kind image type", ad_img._kind({"type": "image"}) == "image")
check("_kind video type", ad_vid._kind({"type": "video"}) == "video")
check("_kind text type", ad_txt._kind({"type": "text"}) == "text")
check("_kind 回退 seededit -> image", ad_img._kind({}) == "image")
check("_kind 回退 seedance -> video", ad_vid._kind({}) == "video")

# ── 4. 图像 payload ──
img_req = {
    "prompt": "一只猫",
    "params": {"resolution": "2K", "n": 1, "aspectRatio": "1:1",
               "reference_images": ["data:image/png;base64,AAAA"]},
}
ip = ad_img._build_image_payload(img_req)
check("image payload.model", ip.get("model") == "seedream-3.0", str(ip))
check("image payload.size 档位式 2K", ip.get("size") == "2K")
check("image payload.response_format == url", ip.get("response_format") == "url")
check("image payload.watermark == False", ip.get("watermark") is False)
check("image payload.n == 1", ip.get("n") == 1)
check("image payload 含 image[] 内联 (img2img)", ip.get("image") == ["data:image/png;base64,AAAA"], str(ip.get("image")))
check("image payload 无 ratio（火山图像不认 ratio）", "ratio" not in ip)

# 无参考图时不应带 image[]
img_req2 = {"prompt": "日落", "params": {"resolution": "3K"}}
ip2 = ad_img._build_image_payload(img_req2)
check("无参考图时无 image[] 键", "image" not in ip2, str(ip2))
check("size 3K 透传", ip2.get("size") == "3K")

# ── 5. 视频 payload ──
vid_req = {
    "prompt": "猫在跑",
    "params": {"duration": 10, "resolution": "2K", "aspectRatio": "16:9",
               "reference_images": ["https://x/y.png", "https://x/z.png"]},
}
vp = ad_vid._build_video_payload(vid_req)
content = vp.get("content", [])
check("video payload.model", vp.get("model") == "seedance-1.0-lite")
check("video content 含 text 段", any(c.get("type") == "text" for c in content), str(content))
check("video content 含 image_url 首帧（仅首张）",
      [c for c in content if c.get("type") == "image_url"][0]["image_url"]["url"] == "https://x/y.png")
check("video 仅取首张（丢弃第二张）", len([c for c in content if c.get("type") == "image_url"]) == 1)
check("video duration 10", vp.get("duration") == 10)
check("video resolution 2K->720p 映射", vp.get("resolution") == "720p", str(vp.get("resolution")))
check("video ratio 16:9 白名单通过", vp.get("ratio") == "16:9")
check("video generate_audio == True", vp.get("generate_audio") is True)
check("video watermark == False", vp.get("watermark") is False)

# ratio 非法 -> adaptive
vp_bad = ad_vid._build_video_payload({"prompt": "x", "params": {"aspectRatio": "99:1"}})
check("video ratio 非法 -> adaptive", vp_bad.get("ratio") == "adaptive", str(vp_bad.get("ratio")))

# duration 越界 clamp
vp_d = ad_vid._build_video_payload({"prompt": "x", "params": {"duration": 999}})
check("video duration 越界 clamp 到 20", vp_d.get("duration") == 20, str(vp_d.get("duration")))
vp_d2 = ad_vid._build_video_payload({"prompt": "x", "params": {"duration": 1}})
check("video duration 越界 clamp 到 5", vp_d2.get("duration") == 5, str(vp_d2.get("duration")))

# ── 6. 余额不足(402) 错误分类（用户当前 key 无钱会命中的分支） ──
friendly, technical = ve._classify_volcengine_error(
    402, {"error": {"code": "InsufficientBalance", "message": "insufficient balance"}}, "image")
check("402 -> 友好'余额不足'", "余额不足" in friendly, friendly)
check("402 -> technical 含 balance", "balance" in technical, technical)

friendly2, _ = ve._classify_volcengine_error(401, {"error": {"message": "unauthorized"}}, "image")
check("401 -> 友好'鉴权失败'", "鉴权" in friendly2, friendly2)

print("\n==== SUMMARY ====")
print(f"PASS={len(PASS)} FAIL={len(FAIL)}")
if FAIL:
    print("FAILURES:")
    for label, detail in FAIL:
        print(f"  - {label} :: {detail}")
    sys.exit(1)
print("ALL_PASS")
