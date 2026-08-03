"""提示词构造层 (Phase2): 图片/视频节点按用户所选平台配置构造平台化提示词.

设计对齐 learn-claude-code 的"注册表 + 钩子分层"哲学:
- 加一个平台 = 在 PromptComposerRegistry 注册一个 compose() 函数, 核心生成调度(dispatch)流程永不动。
- 加一类构造策略 = 注册一个新 mode 的 composer。

两种内置模式 (由 PlatformConfig.prompt_mode 决定):
- plain: 用平台 presets (style_prefix / negative_prompt / aspect_ratio / quality) 模板拼装。
         零额外 LLM 调用, 零额外 token, 最快上线。
- llm:   先调文本 LLM 把用户聊天扩写成平台化描述, 再拼 presets。
         需平台配置 expand_model; 无 expand_model 或扩写失败 -> 自动回退 plain, 保证链路不中断。
"""
from __future__ import annotations

import abc
from typing import Any

import requests

from app import db
from app.config import settings


class BasePromptComposer(abc.ABC):
    mode: str = "base"

    @abc.abstractmethod
    def compose(self, chat: str, presets: dict, req: dict, platform_config: dict) -> str:
        ...


def _assemble(chat: str, presets: dict) -> str:
    """用平台 presets 把提示词拼成平台化描述 (plain 与 llm 共用)。"""
    prefix = (presets.get("style_prefix") or "").strip()
    negative = (presets.get("negative_prompt") or "").strip()
    quality = (presets.get("quality") or "").strip()
    aspect = (presets.get("aspect_ratio") or "").strip()
    parts = [
        p for p in [
            prefix,
            chat.strip(),
            (f"aspect ratio: {aspect}" if aspect else ""),
            (f"negative prompt: {negative}" if negative else ""),
            (f"quality: {quality}" if quality else ""),
        ] if p
    ]
    return "\n".join(parts).strip()


class PlainComposer(BasePromptComposer):
    """模板拼装: 零额外成本, 平台 presets 直接拼到聊天意图上。"""
    mode = "plain"

    def compose(self, chat: str, presets: dict, req: dict, platform_config: dict) -> str:
        return _assemble(chat, presets)


class LlmComposer(BasePromptComposer):
    """llm 扩写: 先调文本 LLM 把聊天扩写成平台化描述, 再套 presets。

    扩写失败 (无 expand_model / 网络错误 / 解析失败) 时自动回退到聊天原文,
    确保不会因为"提示词优化"这个增强功能而阻断主生成链路。
    """
    mode = "llm"

    def compose(self, chat: str, presets: dict, req: dict, platform_config: dict) -> str:
        expanded = _expand_with_llm(chat, platform_config)
        return _assemble(expanded if expanded else chat, presets)


def _expand_with_llm(chat: str, platform_config: dict) -> str | None:
    """用平台配置的 expand_model (ai_models.id) 调文本 LLM 扩写提示词。

    返回扩写文本; 任何异常/缺配置返回 None (调用方回退 plain)。
    """
    expand_model = platform_config.get("expand_model")
    if not expand_model:
        return None
    try:
        cfg = db.get_model_with_provider(expand_model)
    except Exception:  # noqa: BLE001
        return None
    if not cfg or not cfg.get("provider_type"):
        return None
    base = (cfg.get("base_url") or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/v1/chat/completions"
    payload = {
        "model": cfg["model_name"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a prompt engineer. Rewrite the user's short request into a "
                    "detailed, platform-optimized generation prompt. Keep the original intent. "
                    "Output only the prompt, no commentary."
                ),
            },
            {"role": "user", "content": chat},
        ],
    }
    try:
        resp = requests.post(
            url, json=payload,
            headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
            timeout=(settings.provider_http_connect_timeout_s, settings.provider_image_timeout_s),
        )
        if resp.status_code // 100 != 2:
            return None
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001
        return None


class PromptConstructionLayer:
    """提示词构造层单例: 按 mode 选 composer, 无平台配置时原样返回聊天文本。"""

    def __init__(self) -> None:
        self._composers: dict[str, BasePromptComposer] = {
            "plain": PlainComposer(),
            "llm": LlmComposer(),
        }

    def register(self, composer: BasePromptComposer) -> None:
        """扩展点: 加一个新平台/新构造策略, 只注册一个 composer, 不动核心循环。"""
        self._composers[composer.mode] = composer

    def construct(self, req: dict, platform_config: dict | None) -> str:
        chat = (req.get("prompt") or "").strip()
        if not platform_config:
            return chat
        mode = platform_config.get("prompt_mode") or "plain"
        if mode == "llm" and not platform_config.get("expand_model"):
            mode = "plain"  # 无扩写模型 -> 自动回退
        composer = self._composers.get(mode) or self._composers["plain"]
        return composer.compose(chat, platform_config.get("presets_json") or {}, req, platform_config)


# 全局单例 (worker / router 共享)
INSTANCE = PromptConstructionLayer()
