"""AI 路由层: 统一接入外部大模型 (ARCH D5 / ADR-004).

本文件是"编排不出图"原则的核心: orchestrator 只调用外部模型, 不自己生图。

路由策略 (重构后, 按模型驱动):
- 请求携带 model (= ai_models.id); 编排器据此从 DB 解析真实模型名 + 提供商配置。
- provider_type == 'mock'  -> MockProvider (本地占位, 不出网, 联调可用)。
- provider_type == 'openai-compatible' -> OpenAICompatibleProvider (真实调用 Agnes 等)。
- 解析不到模型/提供商停用 -> 视 settings.allow_mock_fallback 决定回退 Mock 还是失败。
- 真实提供商调用失败 -> 直接抛出 (worker 置 FAILED + 退款), 默认不静默回退到 Mock,
  以免给已扣费用户返回假结果并掩盖故障 (allow_mock_fallback=True 时仅供离线联调)。
"""
from __future__ import annotations

import abc
import time
import uuid

from app import db
from app.config import settings


class GenerationResult:
    def __init__(self, url: str, provider: str, raw: dict | None = None, text: str | None = None):
        self.url = url
        self.provider = provider
        self.raw = raw or {}
        self.text = text  # 文本生成结果 (图像/视频为 None)


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
        kind = req.get("type")
        if kind == "video":
            url = f"{settings.cdn_base_url}/mock/{job_id}.mp4"
        elif kind == "text":
            return GenerationResult(
                url="", provider=self.name, text=f"[mock] {req.get('prompt', '')[:200]}"
            )
        else:
            url = f"{settings.cdn_base_url}/mock/{job_id}.png"
        return GenerationResult(url=url, provider=self.name)


_mock = MockProvider()


def _make_real_provider(cfg: dict):
    """按 DB 提供商行构造真实适配器 (延迟导入, 避免与 agnes_provider 形成环)。"""
    from app.agnes_provider import OpenAICompatibleProvider

    return OpenAICompatibleProvider(cfg)


def route(req: dict) -> GenerationResult:
    """按 model 解析提供商并调用; 真实失败按策略决定回退 Mock 还是抛出。"""
    model_id = req.get("model")
    cfg = None
    try:
        cfg = db.get_model_with_provider(model_id) if model_id else None
    except Exception as e:  # noqa: BLE001  DB 抖动不应让整条链路崩, 记录后按缺省处理
        print(f"[router] resolve model '{model_id}' failed: {e}")
        cfg = None

    # 解析不到模型 / 提供商停用 -> Mock 兜底 (仅联调) 或直接失败。
    if not cfg or not cfg.get("provider_enabled"):
        if settings.allow_mock_fallback or (cfg and cfg.get("provider_type") == "mock"):
            return _mock.generate(req)
        raise RuntimeError(f"model '{model_id}' unavailable (not found or provider disabled)")

    provider_type = cfg.get("provider_type")
    if provider_type == "mock":
        return _mock.generate(req)

    if provider_type == "openai-compatible":
        try:
            return _make_real_provider(cfg).generate(req)
        except Exception as e:  # noqa: BLE001
            _emit_fallback_alert(req, cfg.get("provider_name", "provider"), e)
            if settings.allow_mock_fallback:
                return _mock.generate(req)
            raise  # 传播 -> worker 置 FAILED -> 退款

    raise RuntimeError(f"unsupported provider_type: {provider_type}")


def _emit_fallback_alert(req: dict, provider_name: str, err: Exception) -> None:
    try:
        from app.redis_conn import publish_event
        from services.shared.events import notification

        publish_event(notification(
            user_id=int(req.get("user_id", 0) or 0),
            title="生成失败",
            body=f"提供商 `{provider_name}` 调用失败: {str(err)[:160]}",
            level="error",
        ))
    except Exception as e:  # noqa: BLE001
        print(f"[router] emit alert failed: {e}")
