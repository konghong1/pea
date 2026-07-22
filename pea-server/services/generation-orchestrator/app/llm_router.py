"""AI 路由层: 统一接入外部大模型, 失败自动回退 (ARCH D5 / ADR-004 LiteLLM).

本文件是"编排不出图"原则的核心: orchestrator 只调用外部模型, 不自己生图。
真实环境经 LiteLLM 路由 (provider_primary -> provider_fallback); 本地开发用 MockProvider 直接跑通全链路。
"""
from __future__ import annotations

import abc
import time
import uuid

from app.config import settings


class GenerationResult:
    def __init__(self, url: str, provider: str, raw: dict | None = None):
        self.url = url
        self.provider = provider
        self.raw = raw or {}


class BaseProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def generate(self, req: dict) -> GenerationResult:
        ...


class MockProvider(BaseProvider):
    """本地可跑通的占位 provider: 不调外部, 直接返回确定性占位媒体 URL."""
    name = "mock"

    def generate(self, req: dict) -> GenerationResult:
        # 模拟出图耗时
        time.sleep(0.3)
        job_id = req.get("job_id", uuid.uuid4().hex)
        if req.get("type") == "video":
            url = f"{settings.cdn_base_url}/mock/{job_id}.mp4"
        elif req.get("type") == "text":
            url = f"{settings.cdn_base_url}/mock/{job_id}.txt"
        else:
            url = f"{settings.cdn_base_url}/mock/{job_id}.png"
        return GenerationResult(url=url, provider=self.name)


class LiteLLMProvider(BaseProvider):
    """真实 provider 模板: 经 litellm 路由到 MJ/Kling/OpenAI 等。

    实际部署时 `pip install litellm` 并填充 call_llm。失败时抛出, 由 router 切 fallback。
    """

    def __init__(self, litellm_model: str):
        self.name = f"litellm:{litellm_model}"
        self.litellm_model = litellm_model

    def generate(self, req: dict) -> GenerationResult:
        # from litellm import completion  # 真实环境取消注释
        # resp = completion(model=self.litellm_model, messages=[{"role":"user","content":req["prompt"]}])
        # ... 调外部并上传到 S3, 返回 CDN URL
        raise NotImplementedError("LiteLLM provider 需按真实密钥/模型接入")


_PROVIDERS: dict[str, BaseProvider] = {
    "mock": MockProvider(),
}


def get_provider(name: str) -> BaseProvider:
    if name not in _PROVIDERS:
        # 未注册的视为 LiteLLM 模型名
        _PROVIDERS[name] = LiteLLMProvider(name)
    return _PROVIDERS[name]


def route(req: dict) -> GenerationResult:
    """主 provider 失败 -> 自动切 fallback (ARCH 风险 R2)."""
    order = [settings.provider_primary, settings.provider_fallback]
    last_err: Exception | None = None
    for name in order:
        try:
            return get_provider(name).generate(req)
        except Exception as e:  # noqa: BLE001
            last_err = e
            # 发布告警事件 (由 BFF 转通知)
            from app.redis_conn import publish_event
            from services.shared.events import notification
            publish_event(notification(
                user_id=req.get("user_id", 0),
                title="Provider 回退",
                body=f"主 provider `{name}` 失败, 尝试回退。",
                level="warning",
            ))
    raise last_err or RuntimeError("all providers failed")
