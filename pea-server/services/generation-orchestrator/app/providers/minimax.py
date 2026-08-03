"""MiniMax 全模型适配器 (视频 v2/v1 + 图像 + 文本 + 音乐 + 语音).

为什么单独一个文件
------------------
MiniMax 的 API 与 OpenAI 兼容族**形状差异极大**, 硬塞进 OpenAICompatibleProvider
只会污染 Agnes 主流程。按项目既定边界(注册表 + @register_provider), 新厂商
= 一个自洽的适配器文件 + 一行注册, 不碰工厂逻辑。

真实探测得出的接口契约 (2026-08-02, 官方文档缺失部分靠真机 curl 枚举)
--------------------------------------------------------------------
【错误语义: 两套, 必须分别处理 —— 这是最大的坑】
  - v1 全系列 (video/image/music/t2a): **HTTP 恒为 200**, 真实错误藏在
    ``base_resp.status_code`` (0=成功, 2013=参数非法, 1004=鉴权失败...)。
    只看 HTTP 码会把"unsupported model"当成功, 于是扣了费给空结果。
  - v2 视频: 返回**真实 HTTP 码** (400/500) + ``{"type":"error","error":{...}}``。
  ``_raise_for_minimax`` 两者都查, 缺一不可。

【视频 v2 (MiniMax-H3)】
  POST /v2/video_generation
    {model, content:[{type:"text",text} | {type:"image_url",role:"first_frame",
     image_url:{url}}], resolution, duration, ratio, callback_url, aigc_watermark}
    -> {task_id}
  GET  /v2/query/video_generation/{task_id}
    -> {task:{status: queued|running|succeeded|failed|expired, url, ratio,
              usage:{total_seconds}}}
  ✅ 实测 content[].image_url.url **直接吃 data URI base64**。

【视频 v1 (Hailuo / T2V / I2V / S2V / video-01 系列)】
  POST /v1/video_generation  {model, prompt, first_frame_image, duration,
                              resolution, subject_reference}
    -> {task_id, base_resp}
  GET  /v1/query/video_generation?task_id=  -> {status, file_id, base_resp}
  GET  /v1/files/retrieve?file_id=          -> {file:{download_url}, base_resp}
  ⚠️ 两段式: 拿到 file_id 还要再换一次 download_url, 直接给 file_id 前端放不了。
  ✅ 实测 first_frame_image **直接吃 data URI base64**。

【图像 image-01 / image-01-live】
  POST /v1/image_generation {model, prompt, aspect_ratio, n, response_format:"url",
                             prompt_optimizer, subject_reference:[{type:"character",
                             image_file}]}
    -> {data:{image_urls:[]}, base_resp}
  ✅ 实测 subject_reference[].image_file **直接吃 data URI base64**。

【文本 MiniMax-M*】POST /v1/chat/completions (OpenAI 兼容, content 内含 <think> 需剥离)
【音乐 music-*】   POST /v1/music_generation  (lyrics 必填)
【语音 speech-*】  POST /v1/t2a_v2            (output_format:"url")

架构收益: 因为 MiniMax 全线接受 data URI, 参考图走 ``Base64InlineStrategy`` 内联即可,
**无需**像 Agnes 视频那样把图转存公网 + 隧道预检 —— 少一整条故障链
("隧道子域过期 -> 外部拿到 HTML 占位页 -> 晦涩 400")。
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx
import requests

from app.agnes_provider import _apost_with_retry, _api_base, _post_with_retry, _short
from app.async_core.provider_adapter import BaseProviderAdapter, register_provider
from app.async_core.types import (
    AsyncHandle,
    CompletionMode,
    GenerationResult,
    NormalizedStatus,
    PollStatus,
    ProviderCapabilities,
    SubmitOutcome,
)
from app.config import settings
from app.param_adapters import Base64InlineStrategy, normalize_image_params

logger = logging.getLogger(__name__)

# ── 模型路由表 (前缀匹配, 大小写不敏感) ───────────────────────────────
# ⚠️ 联调踩坑: 最初把 v2 前缀写成 "minimax-h", 结果 "MiniMax-Hailuo-02" 也被它匹配,
#    v1 模型被打到 v2 端点拿 400 "该模型暂不支持 /v2/video_generation"。
#    改用正则区分: v2 是 H 系列 + 数字 (MiniMax-H3), v1 的 Hailuo 是 H + 字母。
#    同时 _kind() 里先判 v1 再判 v2, 双保险。
_V2_VIDEO_RE = re.compile(r"^minimax-h\d", re.IGNORECASE)
# v1 视频: 扁平 body + base_resp 错误语义 + file_id 两段取回
_V1_VIDEO_PREFIXES = (
    "minimax-hailuo", "t2v-", "i2v-", "s2v-", "video-01",
)
_IMAGE_PREFIXES = ("image-01",)
_MUSIC_PREFIXES = ("music-",)
_SPEECH_PREFIXES = ("speech-", "t2a")
# 文本/推理模型: M 系列 + 老一代 abab 系列。显式识别而非靠 req['type'] 回落 ——
# 管理员把 MiniMax-M2 误配成 type=video 时也能正确落到 chat/completions。
_TEXT_PREFIXES = ("minimax-m", "abab", "minimax-text")

# 需要 subject_reference 的 v1 视频模型 (S2V 主体参考)
_S2V_PREFIXES = ("s2v-",)

# MiniMax 图像/视频 ratio 白名单 (非白名单值丢弃并告警, 避免 2013 参数错)
_MM_RATIOS = {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"}

# ⚠️ v2 纯文生视频 (t2v) 的 ratio 白名单比通用白名单**窄**, 且该参数**必填**。
#    实测: 不传 ratio -> 400 "t2va(纯文本)场景必须显式指定 ratio 且不能为 adaptive,
#    可用值:16:9/4:3/1:1/3:4/9:16/21:9"。3:2 / 2:3 不在其中。
#    图生视频 (带首帧) 时 ratio 可省略 —— 上游按首帧尺寸自适应, 反而更符合预期。
_V2_T2V_RATIOS = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9")
_V2_T2V_RATIO_DEFAULT = "16:9"

# 前端档位 -> MiniMax resolution 枚举
_TIER_TO_RESOLUTION_V2 = {"1K": "768P", "2K": "1080P", "3K": "2K", "4K": "2K"}
_TIER_TO_RESOLUTION_V1 = {"1K": "768P", "2K": "1080P", "3K": "1080P", "4K": "1080P"}

# 逐模型的 resolution 白名单 —— 各模型支持的档位并不一致, 传错直接 400 (2013)。
# 联调实测: MiniMax-H3 **只**支持 2K, 给 1080P 会被拒。
# 键为小写模型前缀; 未列出的模型不做钳制, 按上面的档位映射直接下发。
_MODEL_RESOLUTIONS: dict[str, tuple[str, ...]] = {
    "minimax-h3": ("2K",),
    # v1 Hailuo: 实测报错原文 "param 'resolution' only support 512P, 768P and 1080P"
    "minimax-hailuo": ("512P", "768P", "1080P"),
}


# 分辨率档位的相对高低 (仅用于"就近降级"排序, 数值本身无物理含义)
_RESOLUTION_RANK = {"512P": 1, "768P": 2, "1080P": 3, "2K": 4, "4K": 5}


def _clamp_resolution(model: str, want: str) -> str:
    """把目标分辨率钳制到该模型真实支持的枚举内。

    与其把用户的 "2K" 原样丢给上游换一个晦涩的 2013, 不如就近降级并留日志 ——
    生成任务能跑完比因为一个枚举值失败更重要。

    降级取"不超过诉求的最高档"; 诉求低于所有可选档时取最低档。
    ⚠️ 不能简单取白名单首项 —— Hailuo 白名单首项是 512P, 用户要 2K 却给 512P
    等于画质塌方, 比报错更让人困惑。
    """
    m = (model or "").lower()
    for prefix, allowed in _MODEL_RESOLUTIONS.items():
        if not m.startswith(prefix):
            continue
        if want in allowed:
            return want
        want_rank = _RESOLUTION_RANK.get(want, 0)
        not_above = [a for a in allowed if _RESOLUTION_RANK.get(a, 0) <= want_rank]
        picked = (
            max(not_above, key=lambda a: _RESOLUTION_RANK.get(a, 0))
            if not_above
            else min(allowed, key=lambda a: _RESOLUTION_RANK.get(a, 0))
        )
        logger.info(
            "[minimax] %s 不支持 resolution=%s, 就近调整为 %s (支持: %s)",
            model, want, picked, ",".join(allowed),
        )
        return picked
    return want

# v1 视频状态 -> 归一化
_V1_STATUS_DONE = {"success"}
_V1_STATUS_FAIL = {"fail", "failed", "expired", "unknown"}
# v2 视频状态 -> 归一化
_V2_STATUS_DONE = {"succeeded", "success"}
_V2_STATUS_FAIL = {"failed", "fail", "expired", "cancelled", "canceled"}

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)


def _model_matches(model: str, prefixes: tuple[str, ...]) -> bool:
    m = (model or "").strip().lower()
    return any(m.startswith(p) for p in prefixes)


def _strip_think(text: str) -> tuple[str, bool]:
    """剥离 MiniMax M 系列返回内容里的 <think>...</think> 推理块。

    模型把思维链直接塞在 content 里, 原样透传会让用户看到大段自言自语。

    返回 ``(正文, 是否被思考块吃光)``。第二个标志很关键 —— M 系列是推理模型,
    当 ``max_tokens`` 给得太小(联调实测 300 就会触发), 全部预算会烧在思考阶段,
    ``</think>`` 都没输出就被截断, 剥离后正文为空。此时**必须**让调用方知道,
    否则就是"扣了费返回空字符串", 比报错更糟。
    """
    if not text:
        return "", False
    out = _THINK_RE.sub("", text)
    # 未闭合残留: "<think> 一堆..." 且始终没有 </think> (被 max_tokens 截断)
    truncated_in_think = "<think>" in out and "</think>" not in out
    if truncated_in_think:
        out = out.split("<think>", 1)[0]
    out = out.strip()
    starved = (not out) and bool(text.strip())
    return out, starved


def _classify_minimax_error(resp, what: str, body: dict | None) -> tuple[str, str]:
    """把上游原始错误归类为 ``(friendly_msg, technical)`` 二元组。

    - ``friendly_msg`` — 给前端 toast 的简短中文消息（≤ 60 字符）。前端 UI
      空间有限, 把 200+ 字符的 JSON 原文糊上去会被截断/溢出。
    - ``technical`` — 完整原始错误（含 request_id / type / message / base_resp），
      仅用于 logger 排查, 不向前端暴露。

    归类来源: MiniMax 官方 base_resp.status_code 语义 + HTTP 4xx/5xx 网关层。
    1008 / insufficient_balance = 余额不足, 1004 = 鉴权失败, 2013 = 参数非法。
    """
    # 先尝试从 body 提取结构化字段
    err = body.get("error") if isinstance(body, dict) else None
    err_type = (err.get("type") if isinstance(err, dict) else None) or (
        body.get("type") if isinstance(body, dict) else None
    )
    err_msg = (err.get("message") if isinstance(err, dict) else None) or (
        body.get("message") if isinstance(body, dict) else None
    )
    base_resp = body.get("base_resp") if isinstance(body, dict) else None
    base_code = base_resp.get("status_code") if isinstance(base_resp, dict) else None
    base_msg = base_resp.get("status_msg") if isinstance(base_resp, dict) else None
    request_id = body.get("request_id") if isinstance(body, dict) else None

    # 余额不足（最常见，单独优先匹配）
    if resp.status_code == 402 or err_type == "insufficient_balance_error" or base_code == 1008:
        friendly = "MiniMax 账户余额不足，请联系管理员充值后重试"
        technical = (
            f"insufficient balance | http={resp.status_code} err_type={err_type} "
            f"base_code={base_code} request_id={request_id} msg={err_msg or base_msg}"
        )
        return friendly, technical

    # 鉴权失败
    if resp.status_code in (401, 403) or base_code in (1004, 1007):
        friendly = "MiniMax 鉴权失败，请检查 API 密钥是否有效"
        technical = (
            f"auth failed | http={resp.status_code} base_code={base_code} "
            f"request_id={request_id} msg={err_msg or base_msg}"
        )
        return friendly, technical

    # 限流
    if resp.status_code == 429 or base_code in (1006,):
        friendly = "MiniMax 限流，请稍后再试"
        technical = (
            f"rate limited | http={resp.status_code} base_code={base_code} "
            f"request_id={request_id} msg={err_msg or base_msg}"
        )
        return friendly, technical

    # 参数非法
    if resp.status_code == 400 or base_code in (2013, 1002):
        friendly = "MiniMax 参数错误，请检查模型参数（时长/分辨率/参考图等）"
        technical = (
            f"invalid params | http={resp.status_code} base_code={base_code} "
            f"request_id={request_id} msg={err_msg or base_msg}"
        )
        return friendly, technical

    # 上游服务异常
    if resp.status_code // 100 == 5:
        friendly = "MiniMax 服务暂不可用，请稍后再试"
        technical = (
            f"upstream 5xx | http={resp.status_code} request_id={request_id} "
            f"msg={err_msg or base_msg}"
        )
        return friendly, technical

    # 其他兜底
    friendly = f"MiniMax 调用失败（HTTP {resp.status_code}）"
    technical = (
        f"unknown error | http={resp.status_code} base_code={base_code} "
        f"err_type={err_type} request_id={request_id} msg={err_msg or base_msg}"
    )
    return friendly, technical


def _raise_for_minimax(resp, what: str, body: dict | None = None) -> dict:
    """MiniMax 双错误语义统一检查 —— v1 看 base_resp, v2 看 HTTP 码。

    返回解析后的 JSON body (调用方不用再 .json() 一次)。
    任一层判定失败都抛 RuntimeError, 由上层置 FAILED 并触发退款,
    绝不静默返回空结果 (扣费给假图是不可接受的)。

    抛出时 RuntimeError 的 message 是**友好摘要**（≤ 60 字符, 适配前端 toast 宽度）。
    完整原始错误（含 request_id / type / base_resp）只进 logger, 不向前端暴露。
    """
    # ① v2 / 网关层: 真实 HTTP 错误码
    if resp.status_code // 100 != 2:
        txt = ""
        try:
            txt = resp.text[:200]
        except Exception:  # noqa: BLE001
            pass
        reason = getattr(resp, "reason_phrase", None) or getattr(resp, "reason", "") or "upstream error"
        # HTML 错误页（Cloudflare / 网关降级）直接当上游异常报
        if txt.lstrip().startswith(("<!DOCTYPE", "<!doctype", "<html", "<HTML")):
            friendly = f"MiniMax 网关返回异常（HTTP {resp.status_code}）"
            technical = f"html error page | http={resp.status_code} reason={reason}"
            logger.warning("[minimax] %s %s | technical=%s", what, friendly, technical)
            raise RuntimeError(friendly)

        # JSON 体错误 → 用归类器生成友好消息
        try:
            parsed = resp.json()
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            friendly, technical = _classify_minimax_error(resp, what, parsed)
            logger.warning("[minimax] %s %s | technical=%s | body=%s",
                           what, friendly, technical, txt[:200])
            raise RuntimeError(friendly)

        # 非 JSON 也非 HTML，罕见
        friendly = f"MiniMax 调用失败（HTTP {resp.status_code}）"
        technical = f"non-json error | http={resp.status_code} txt={txt[:120]}"
        logger.warning("[minimax] %s %s | technical=%s", what, friendly, technical)
        raise RuntimeError(friendly)

    if body is None:
        try:
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"minimax {what} 响应非 JSON: {_short(getattr(resp, 'text', ''))}") from exc

    if not isinstance(body, dict):
        raise RuntimeError(f"minimax {what} 响应结构异常: {_short(body)}")

    # ② v2 错误体: HTTP 200 也可能带 {"type":"error", ...} (极少数网关行为)
    if body.get("type") == "error":
        err = body.get("error") or {}
        # 用归类器把 Anthropic-style 错误也归类成友好消息
        friendly, technical = _classify_minimax_error(resp, what, body)
        logger.warning("[minimax] %s %s | technical=%s | body=%s",
                       what, friendly, technical, _short(body))
        raise RuntimeError(friendly)

    # ③ v1 核心陷阱: HTTP 200 + base_resp.status_code != 0 才是真实错误
    br = body.get("base_resp")
    if isinstance(br, dict):
        code = br.get("status_code")
        if code not in (0, None):
            friendly, technical = _classify_minimax_error(resp, what, body)
            logger.warning("[minimax] %s %s | technical=%s | body=%s",
                           what, friendly, technical, _short(body))
            raise RuntimeError(friendly)
    return body


def _clamp(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


@register_provider("vendor-native", "minimax")
class MiniMaxAdapter(BaseProviderAdapter):
    """MiniMax 全模型适配器: 一个厂商(vendor=minimax)覆盖文本/图像/视频/音乐/语音。

    注册键为 ("vendor-native", "minimax") —— 协议=vendor-native (厂商自有协议),
    厂商=minimax。与前端「协议=厂商原生协议」「厂商=MiniMax」两个下拉一一对应。

    完成模式声明为 POLL —— 视频异步走句柄轮询; 图像/文本/音乐/语音在
    ``submit`` 里直接 ``SubmitOutcome(sync=True)`` 返回, 不进句柄表
    (与 AgnesAdapter 同构, Dispatcher 已按 outcome.sync 分流)。
    """

    # MiniMax 全线接受 data URI, 内联即可, 不需要公网转存
    ref_strategy = Base64InlineStrategy()

    # ── 契约声明 ────────────────────────────────────────────────
    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            completion_mode=CompletionMode.POLL,
            # v2 支持 callback_url, 但回调需公网可达; 未配 webhook_base_url 时
            # 自动退化为纯轮询 (WebhookCapableMixin 的判定逻辑)。
            accepts_callback=bool(settings.webhook_base_url),
            status_query_template="/v2/query/video_generation/{task_id}",
        )

    def resolve_refs(self, refs: list[str]) -> list[str]:
        """覆写: MiniMax 直接吃 data URI, 不做公网转存 (省掉隧道依赖)。"""
        return self.ref_strategy.resolve(refs, provider=self)

    # ── HTTP 基建 ───────────────────────────────────────────────
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return _api_base(self.base_url, path)

    # ── 类型分发 ────────────────────────────────────────────────
    def _kind(self, req: dict) -> str:
        """确定实际要走的 MiniMax 端点族。

        ⚠️ 排查背景 (2026-08-03): 用户报 H3 走到了 v1 路径 (base_resp 1008),
        几乎都是数据库 ``ai_models.model_name`` 被改成了 ``minimax-hailuo-3``
        之类的名称 —— 前端显示名是 H3, 但 model_name 又带 hailuo 前缀, 导致
        v1 命中。代码上没错, 但配置错乱被默默掩盖, 用户看到的是 "余额不足"
        而不是 "模型走错端点了"。

        故 _kind 加 [minimax-route] 日志: 视频族决策必须可观测, 遇到反直觉
        组合 (H+数字 同时匹配 v1/v2) 时打 ERROR, 让运维一眼看到根因。
        """
        model = (self.model_name or "").strip()
        # ⚠️ 顺序要紧: 先判更具体的 v1 前缀 (minimax-hailuo...), 再判 v2 正则,
        #    否则 Hailuo 系列会被误判成 H 系列 (见 _V2_VIDEO_RE 注释里的联调事故)。
        if _model_matches(model, _V1_VIDEO_PREFIXES):
            # 配置错乱检测: 若 model 同样满足 v2 正则 (H + 数字), 几乎可
            # 肯定是把 "MiniMax-H3" 误存为 "minimax-hailuo-3" 的拼写事故.
            # v1 端点上即便调通, 也会以 v1 价格 / 计费 / capability 计费.
            if _V2_VIDEO_RE.match(model):
                logger.error(
                    "[minimax-route] 路由冲突: model=%r 同时命中 v1 (minimax-hailuo 前缀) "
                    "与 v2 (minimax-h\\d 正则); 按当前顺序走 v1. "
                    "请检查 ai_models.model_name —— 前端显示名是 H3 时, model_name "
                    "应当是 'MiniMax-H3', 千万**不要**带 hailuo 前缀 (minimax-hailuo-3).",
                    model,
                )
            else:
                logger.info("[minimax-route] model=%s -> video_v1 (前缀命中)", model)
            return "video_v1"
        if _V2_VIDEO_RE.match(model):
            logger.info("[minimax-route] model=%s -> video_v2 (H+数字 正则命中)", model)
            return "video_v2"
        if _model_matches(model, _IMAGE_PREFIXES):
            return "image"
        if _model_matches(model, _MUSIC_PREFIXES):
            return "music"
        if _model_matches(model, _SPEECH_PREFIXES):
            return "speech"
        if _model_matches(model, _TEXT_PREFIXES):
            return "text"
        # model 名没给出线索 -> 回落到前端声明的 type
        t = (req.get("type") or "image").lower()
        if t == "video":
            return "video_v2"
        if t == "text":
            return "text"
        if t == "audio":
            return "music"
        return "image" if t == "image" else "text"

    async def submit(self, req: dict) -> "SubmitOutcome":
        kind = self._kind(req)
        if kind == "video_v2":
            return await self._submit_video_v2(req)
        if kind == "video_v1":
            return await self._submit_video_v1(req)
        if kind == "image":
            return SubmitOutcome(sync=True, result=await self._gen_image(req))
        if kind == "music":
            return SubmitOutcome(sync=True, result=await self._gen_music(req))
        if kind == "speech":
            return SubmitOutcome(sync=True, result=await self._gen_speech(req))
        return SubmitOutcome(sync=True, result=await self._gen_text(req))

    # ── 视频 v2 (MiniMax-H3): 多模态 content 数组 ──────────────────
    def _build_v2_payload(self, req: dict) -> dict:
        p = req.get("params") or {}
        content: list[dict] = [{"type": "text", "text": req.get("prompt") or ""}]

        refs = self.ref_strategy.resolve(p.get("reference_images") or [], provider=self)
        # ── v2 content[] 角色映射 (前端 gen_mode -> MiniMax v2 角色) ──
        # 前端 NodeChatPrompt.tsx L1347 把选项写入 params.gen_mode, 取值:
        #   'first_last' (首尾帧模式) -> 第1张 first_frame + 末张 last_frame
        #   'full_ref'   (全能参考模式, 默认) -> 仅首张 reference_image (主体参考)
        # ⚠️ 两套角色互斥, 绝不可混用 —— 否则 400
        #    "reference 场景不能混用 first_frame/middle_frame/last_frame, 请二选一(2013)"
        # 联调事故 (2026-08-03): 旧代码**无视 gen_mode**, 多图时第1张塞 first_frame、
        # 第2+张塞 reference_image, 两角色并存直接触发上面的 400. 本版严格按用户选择映射.
        gen_mode = (str(p.get("gen_mode") or "full_ref")).strip().lower()
        n_refs = len(refs)
        if gen_mode == "first_last":
            # 首尾帧模式: 严格 first_frame + last_frame 两段式, 不与 reference_image 混用
            if n_refs >= 1:
                content.append({
                    "type": "image_url",
                    "role": "first_frame",
                    "image_url": {"url": refs[0]},
                })
            if n_refs >= 2:
                content.append({
                    "type": "image_url",
                    "role": "last_frame",
                    "image_url": {"url": refs[-1]},
                })
            if n_refs > 2:
                logger.warning(
                    "[minimax] v2 首尾帧模式收到 %d 张参考图, 仅取首尾 2 张下发, "
                    "丢弃中间 %d 张 (model=%s)",
                    n_refs, n_refs - 2, self.model_name,
                )
        else:  # full_ref 全能参考 (默认): 单张主体参考, 不混用首/末帧
            if n_refs >= 1:
                content.append({
                    "type": "image_url",
                    "role": "reference_image",
                    "image_url": {"url": refs[0]},
                })
            if n_refs > 1:
                logger.warning(
                    "[minimax] v2 全能参考模式仅支持单张主体参考图, 丢弃其余 %d 张 (model=%s)",
                    n_refs - 1, self.model_name,
                )

        payload: dict[str, Any] = {
            "model": self.model_name,
            "content": content,
            "duration": _clamp(p.get("duration"), 4, 15, 6),
        }
        tier = (p.get("resolution") or p.get("size") or "").upper()
        payload["resolution"] = _clamp_resolution(
            self.model_name, _TIER_TO_RESOLUTION_V2.get(tier, "1080P")
        )
        # ── ratio: 纯文生视频必填, 图生视频可省 ──────────────────────
        # 实测 400: "t2va(纯文本)场景必须显式指定 ratio 且不能为 adaptive"。
        # 有首帧时不传, 让上游按首帧尺寸自适应 (强行指定反而会裁剪用户的图)。
        is_t2v = not any(c.get("type") == "image_url" for c in content)
        ratio = (p.get("aspectRatio") or "").strip()
        if is_t2v:
            if ratio not in _V2_T2V_RATIOS:
                if ratio:
                    logger.info(
                        "[minimax] t2v 不支持 ratio=%s, 回退 %s (可用: %s)",
                        ratio, _V2_T2V_RATIO_DEFAULT, "/".join(_V2_T2V_RATIOS),
                    )
                ratio = _V2_T2V_RATIO_DEFAULT
            payload["ratio"] = ratio
        elif ratio:
            if ratio in _MM_RATIOS:
                payload["ratio"] = ratio
            else:
                logger.warning("[minimax] 不支持的 ratio=%s, 已丢弃", ratio)
        if p.get("watermark") is not None:
            payload["aigc_watermark"] = bool(p.get("watermark"))
        return payload

    async def _submit_video_v2(self, req: dict) -> "SubmitOutcome":
        from app.async_core.engine import get_client

        payload = self._build_v2_payload(req)
        url = self._url("/v2/video_generation")
        resp = await _apost_with_retry(
            get_client(), url, payload, self._headers(),
            httpx.Timeout(settings.provider_video_submit_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_minimax(resp, "video-v2 submit")
        task_id = data.get("task_id") or (data.get("task") or {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"minimax video-v2 未返回 task_id: {_short(data)}")
        logger.info("[minimax] v2 video submitted task_id=%s model=%s", task_id, self.model_name)
        return SubmitOutcome(sync=False, handle=AsyncHandle(
            job_id=req.get("job_id", ""),
            user_id=int(req.get("user_id", 0) or 0),
            provider=self.provider_name,
            completion_mode=CompletionMode.POLL,
            provider_task_id=str(task_id),
            status_query=self._url(f"/v2/query/video_generation/{task_id}"),
        ))

    # ── 视频 v1 (Hailuo / T2V / I2V / S2V): 扁平 body + file_id 两段取回 ──
    def _build_v1_payload(self, req: dict) -> dict:
        p = req.get("params") or {}
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": req.get("prompt") or "",
        }
        refs = self.ref_strategy.resolve(p.get("reference_images") or [], provider=self)
        # v1 Hailuo/T2V/I2V/S2V 仅支持首帧 (first_frame_image 字段), 无末帧概念.
        # gen_mode 在 v1 上只影响"末帧是否被忽略"的提示, 首帧行为保持一致.
        gen_mode = (str(p.get("gen_mode") or "full_ref")).strip().lower()
        if refs:
            if _model_matches(self.model_name, _S2V_PREFIXES):
                # S2V-01: 主体参考走 subject_reference, 不是首帧
                payload["subject_reference"] = [{"type": "character", "image": [refs[0]]}]
                if gen_mode == "first_last" and len(refs) >= 2:
                    logger.warning(
                        "[minimax] v1 S2V 模型 %s 仅支持主体参考, '首尾帧'模式的末帧参数被忽略",
                        self.model_name,
                    )
            else:
                # Hailuo v1 (T2V/I2V) 仅支持首帧 (first_frame_image), 无末帧概念
                payload["first_frame_image"] = refs[0]
                if gen_mode == "first_last" and len(refs) >= 2:
                    logger.warning(
                        "[minimax] v1 模型 %s 仅支持首帧 (first_frame_image), 不支持末帧; "
                        "'首尾帧'模式的末帧参数被忽略 (model=%s)",
                        self.model_name, self.model_name,
                    )
                elif len(refs) > 1:
                    logger.info(
                        "[minimax] v1 模型 %s 仅取首张参考图作为首帧, 其余 %d 张丢弃",
                        self.model_name, len(refs) - 1,
                    )

        dur = _clamp(p.get("duration"), 6, 10, 6)
        payload["duration"] = 10 if dur > 6 else 6  # v1 仅 6/10 两档
        tier = (p.get("resolution") or p.get("size") or "").upper()
        res = _TIER_TO_RESOLUTION_V1.get(tier, "768P")
        # 512P 官方仅在带首帧时受理; 无首帧强制抬到 768P 避免 2013
        if res == "512P" and "first_frame_image" not in payload:
            res = "768P"
        payload["resolution"] = _clamp_resolution(self.model_name, res)
        if p.get("watermark") is not None:
            payload["aigc_watermark"] = bool(p.get("watermark"))
        return payload

    async def _submit_video_v1(self, req: dict) -> "SubmitOutcome":
        from app.async_core.engine import get_client

        payload = self._build_v1_payload(req)
        url = self._url("/v1/video_generation")
        resp = await _apost_with_retry(
            get_client(), url, payload, self._headers(),
            httpx.Timeout(settings.provider_video_submit_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_minimax(resp, "video-v1 submit")
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"minimax video-v1 未返回 task_id: {_short(data)}")
        logger.info("[minimax] v1 video submitted task_id=%s model=%s", task_id, self.model_name)
        return SubmitOutcome(sync=False, handle=AsyncHandle(
            job_id=req.get("job_id", ""),
            user_id=int(req.get("user_id", 0) or 0),
            provider=self.provider_name,
            completion_mode=CompletionMode.POLL,
            provider_task_id=str(task_id),
            status_query=self._url(f"/v1/query/video_generation?task_id={task_id}"),
        ))

    # ── 状态查询 (Completer 后台线程调用, 同步实现) ─────────────────
    def query_status(self, handle: AsyncHandle) -> PollStatus:
        sq = handle.status_query or ""
        is_v2 = "/v2/" in sq
        resp = requests.get(
            sq, headers=self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, 60),
            proxies={"http": None, "https": None},
        )
        data = _raise_for_minimax(resp, "video status")
        return self._parse_v2_status(data) if is_v2 else self._parse_v1_status(data)

    @staticmethod
    def _parse_v2_status(data: dict) -> PollStatus:
        task = data.get("task") or data
        raw = str(task.get("status") or "").strip().lower()
        if raw in _V2_STATUS_DONE:
            url = task.get("url") or task.get("video_url") or ""
            if not url:
                return PollStatus(
                    normalized=NormalizedStatus.FAILED, raw_status=raw,
                    error=f"v2 已完成但无下载地址: {_short(task)}",
                )
            return PollStatus(normalized=NormalizedStatus.DONE, raw_status=raw, result_url=url)
        if raw in _V2_STATUS_FAIL:
            return PollStatus(
                normalized=NormalizedStatus.FAILED, raw_status=raw,
                error=task.get("error") or task.get("message") or f"video {raw}",
            )
        return PollStatus(
            normalized=NormalizedStatus.PROCESSING if raw == "running" else NormalizedStatus.PENDING,
            raw_status=raw or "queued",
            progress=task.get("progress"),
        )

    def _parse_v1_status(self, data: dict) -> PollStatus:
        raw = str(data.get("status") or "").strip()
        low = raw.lower()
        if low in _V1_STATUS_DONE:
            file_id = data.get("file_id")
            if not file_id:
                return PollStatus(
                    normalized=NormalizedStatus.FAILED, raw_status=raw,
                    error=f"v1 已完成但无 file_id: {_short(data)}",
                )
            # 两段取回: file_id -> download_url。在此同步完成, 对 Completer 透明。
            return PollStatus(
                normalized=NormalizedStatus.DONE, raw_status=raw,
                result_url=self._retrieve_file_url(str(file_id)),
            )
        if low in _V1_STATUS_FAIL:
            return PollStatus(
                normalized=NormalizedStatus.FAILED, raw_status=raw,
                error=data.get("status_msg") or f"video {raw}",
            )
        # Preparing / Queueing / Processing
        return PollStatus(
            normalized=NormalizedStatus.PROCESSING if low == "processing" else NormalizedStatus.PENDING,
            raw_status=raw or "Queueing",
        )

    def _retrieve_file_url(self, file_id: str) -> str:
        """v1 专属第二段: file_id -> 可下载的 download_url。"""
        resp = requests.get(
            self._url(f"/v1/files/retrieve?file_id={file_id}"),
            headers=self._headers(),
            timeout=(settings.provider_http_connect_timeout_s, 60),
            proxies={"http": None, "https": None},
        )
        data = _raise_for_minimax(resp, "files/retrieve")
        f = data.get("file") or {}
        url = f.get("download_url") or f.get("backup_download_url") or ""
        if not url:
            raise RuntimeError(f"minimax files/retrieve 无 download_url: {_short(data)}")
        return url

    # ── 图像 ────────────────────────────────────────────────────
    async def _gen_image(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        norm = normalize_image_params(req)
        refs = self.ref_strategy.resolve(norm.reference_images, provider=self)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": norm.prompt,
            "n": _clamp(norm.n, 1, 9, 1),
            "response_format": "url",
            "prompt_optimizer": True,
        }
        ratio = norm.aspect_ratio
        if ratio and ratio in _MM_RATIOS:
            payload["aspect_ratio"] = ratio
        elif ratio:
            logger.warning("[minimax] 图像不支持的 ratio=%s, 已丢弃", ratio)
        if norm.seed is not None:
            payload["seed"] = norm.seed
        if refs:
            # image-01 的主体参考: 仅取首图 (官方只认单主体)
            payload["subject_reference"] = [{"type": "character", "image_file": refs[0]}]
            logger.info("[minimax] image subject_reference 已内联 base64 (%d 张候选)", len(refs))

        resp = await _apost_with_retry(
            get_client(), self._url("/v1/image_generation"), payload, self._headers(),
            httpx.Timeout(settings.provider_image_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=settings.provider_image_retry_attempts,
        )
        data = _raise_for_minimax(resp, "image")
        urls = ((data.get("data") or {}).get("image_urls")) or []
        urls = [u for u in urls if isinstance(u, str) and u.startswith("http")]
        if not urls:
            raise RuntimeError(f"minimax image 未返回图片地址: {_short(data)}")
        return GenerationResult(
            url=urls[0], urls=urls, provider=self.provider_name,
            raw={"id": data.get("id")}, usage=self._norm_usage(data),
        )

    # ── 文本 (OpenAI 兼容路径) ───────────────────────────────────
    async def _gen_text(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        p = req.get("params") or {}
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": req.get("prompt") or ""}],
        }
        if p.get("system"):
            payload["messages"].insert(0, {"role": "system", "content": p["system"]})
        # M 系列是推理模型: max_tokens 太小会让预算全烧在 <think> 里, 正文为空。
        # 默认给 8192, 且下限抬到 1024 —— 比返回空文本再退款划算得多。
        payload["max_tokens"] = _clamp(p.get("max_tokens") or 8192, 1024, 1_000_000, 8192)
        if p.get("temperature") is not None:
            payload["temperature"] = float(p["temperature"])

        resp = await _apost_with_retry(
            get_client(), self._url("/v1/chat/completions"), payload, self._headers(),
            httpx.Timeout(300, connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_minimax(resp, "text")
        try:
            choice = data["choices"][0]
            msg = choice.get("message") or {}
            raw_content = msg.get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"minimax text 响应结构异常: {_short(data)}") from exc

        content, starved = _strip_think(raw_content)
        if starved:
            # 正文被推理块吃光 —— 绝不返回空字符串糊弄调用方(那等于扣费给空结果)。
            # 部分部署会把推理放在独立的 reasoning_content 字段, 先兜一次。
            alt = (msg.get("reasoning_content") or "").strip()
            if alt:
                content = alt
            else:
                raise RuntimeError(
                    f"minimax text 正文为空: {self.model_name} 是推理模型, "
                    f"max_tokens={payload.get('max_tokens')} 被 <think> 阶段耗尽 "
                    f"(finish_reason={choice.get('finish_reason')})。请调大 max_tokens。"
                )
        if not content.strip():
            raise RuntimeError(f"minimax text 返回空内容: {_short(data)}")
        return GenerationResult(
            url="", provider=self.provider_name, raw={}, text=content,
            usage=self._norm_usage(data),
        )

    # ── 音乐 ────────────────────────────────────────────────────
    async def _gen_music(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        p = req.get("params") or {}
        lyrics = p.get("lyrics") or req.get("prompt") or ""
        if not lyrics.strip():
            raise RuntimeError("minimax music 需要 lyrics (歌词) 或 prompt")
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": p.get("style") or req.get("prompt") or "pop",
            "lyrics": lyrics,
            "audio_setting": {
                "sample_rate": _clamp(p.get("sample_rate"), 16000, 44100, 44100),
                "bitrate": _clamp(p.get("bitrate"), 32000, 256000, 256000),
                "format": p.get("format") or "mp3",
            },
            "output_format": "url",
        }
        resp = await _apost_with_retry(
            get_client(), self._url("/v1/music_generation"), payload, self._headers(),
            httpx.Timeout(settings.provider_image_timeout_s,
                          connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_minimax(resp, "music")
        audio = (data.get("data") or {}).get("audio") or ""
        if not isinstance(audio, str) or not audio.startswith("http"):
            raise RuntimeError(f"minimax music 未返回音频地址: {_short(data)}")
        return GenerationResult(url=audio, provider=self.provider_name,
                                raw={"trace_id": data.get("trace_id")},
                                usage=self._norm_usage(data))

    # ── 语音 TTS ────────────────────────────────────────────────
    async def _gen_speech(self, req: dict) -> GenerationResult:
        from app.async_core.engine import get_client

        p = req.get("params") or {}
        payload: dict[str, Any] = {
            "model": self.model_name,
            "text": req.get("prompt") or "",
            "stream": False,
            "output_format": "url",
            "voice_setting": {
                "voice_id": p.get("voice_id") or "male-qn-qingse",
                "speed": float(p.get("speed") or 1.0),
                "vol": float(p.get("volume") or 1.0),
                "pitch": _clamp(p.get("pitch"), -12, 12, 0),
            },
            "audio_setting": {
                "sample_rate": _clamp(p.get("sample_rate"), 8000, 44100, 32000),
                "bitrate": _clamp(p.get("bitrate"), 32000, 256000, 128000),
                "format": p.get("format") or "mp3",
            },
        }
        resp = await _apost_with_retry(
            get_client(), self._url("/v1/t2a_v2"), payload, self._headers(),
            httpx.Timeout(300, connect=settings.provider_http_connect_timeout_s),
            max_attempts=2,
        )
        data = _raise_for_minimax(resp, "speech")
        audio = (data.get("data") or {}).get("audio") or ""
        if not isinstance(audio, str) or not audio.startswith("http"):
            raise RuntimeError(f"minimax speech 未返回音频地址: {_short(data)}")
        return GenerationResult(url=audio, provider=self.provider_name,
                                raw={"trace_id": data.get("trace_id")},
                                usage=self._norm_usage(data))

    # ── usage 归一 ──────────────────────────────────────────────
    @staticmethod
    def _norm_usage(data: dict) -> dict:
        """把 MiniMax 各端点的 usage 归一成 {input_tokens,output_tokens,total_tokens}。

        文本端返回 OpenAI 形状 (prompt_tokens/completion_tokens);
        媒体端多为 {total_seconds} 或缺失 —— 缺失时返回空 dict, 由计费层按套餐兜底。
        """
        u = data.get("usage")
        if not isinstance(u, dict):
            return {}
        if "prompt_tokens" in u or "completion_tokens" in u:
            pt = int(u.get("prompt_tokens") or 0)
            ct = int(u.get("completion_tokens") or 0)
            return {
                "input_tokens": pt,
                "output_tokens": ct,
                "total_tokens": int(u.get("total_tokens") or (pt + ct)),
            }
        return dict(u)
