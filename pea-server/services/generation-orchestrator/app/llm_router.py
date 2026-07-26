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
from app.prompt_construction import INSTANCE as prompt_layer


class GenerationResult:
    def __init__(self, url: str, provider: str, urls: list[str] | None = None, raw: dict | None = None, text: str | None = None,
                 usage: dict | None = None):
        self.url = url
        self.urls = urls or []   # 多图生成时所有图片 URL
        self.provider = provider
        self.raw = raw or {}
        self.text = text  # 文本生成结果 (图像/视频为 None)
        self.usage = usage or {}  # token 用量 (Phase3): {input_tokens, output_tokens, total_tokens}


class BaseProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def generate(self, req: dict) -> GenerationResult:
        ...


class MockProvider(BaseProvider):
    """本地可跑通的占位 provider: 不调外部, 直接返回确定性占位媒体 URL.

    占位图改为自包含 data-URI SVG, 浏览器可直接渲染, 不依赖对象存储里是否存在该文件。
    (原实现返回 cdn_base_url/mock/<id>.png, 该文件在 minio 中不存在 -> 画廊/画布显示裂图。)
    """
    name = "mock"

    def generate(self, req: dict) -> GenerationResult:
        # 模拟出图耗时
        time.sleep(0.3)
        job_id = req.get("job_id", uuid.uuid4().hex)
        kind = req.get("type")
        # 从参数中获取出图数量
        n = 1
        try:
            n = max(1, min(4, int(req.get("params", {}).get("n", 1))))
        except (TypeError, ValueError):
            n = 1
        # mock 模式也产出占位 usage, 便于无密钥联调时验证 token 计量链路
        usage = {
            "input_tokens": max(1, len(req.get("prompt", "")) // 4),
            "output_tokens": 0,
            "total_tokens": max(1, len(req.get("prompt", "")) // 4),
        }
        if kind == "video":
            url = f"{settings.cdn_base_url}/mock/{job_id}.mp4"
            return GenerationResult(url=url, provider=self.name, usage=usage)
        elif kind == "text":
            return GenerationResult(
                url="", provider=self.name, text=f"[mock] {req.get('prompt', '')[:200]}",
                usage=usage,
            )
        else:
            # 图片生成：支持多张
            urls = [self._placeholder_image(f"{job_id}_{i}", req.get("prompt", "")) for i in range(n)]
            return GenerationResult(
                url=urls[0],
                urls=urls,
                provider=self.name,
                usage=usage
            )

    @staticmethod
    def _placeholder_image(job_id: str, prompt: str) -> str:
        from urllib.parse import quote

        safe = (prompt or "pea mock").replace("\n", " ")[:48]
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='512' height='512'>"
            "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            "<stop offset='0' stop-color='#1fa2dc'/>"
            "<stop offset='1' stop-color='#8b5cf6'/>"
            "</linearGradient></defs>"
            "<rect width='512' height='512' rx='28' fill='url(#g)'/>"
            "<text x='50%' y='46%' fill='white' font-size='30' font-family='sans-serif' "
            "text-anchor='middle' font-weight='700'>pea 生成预览</text>"
            f"<text x='50%' y='55%' fill='white' font-size='17' font-family='sans-serif' "
            f"text-anchor='middle' opacity='0.9'>{safe}</text>"
            f"<text x='50%' y='92%' fill='white' font-size='13' font-family='sans-serif' "
            f"text-anchor='middle' opacity='0.6'>{job_id[:8]}</text>"
            "</svg>"
        )
        return "data:image/svg+xml;utf8," + quote(svg)


_mock = MockProvider()


def _make_real_provider(cfg: dict):
    """按 DB 提供商行构造真实适配器 (延迟导入, 避免与 agnes_provider 形成环)。"""
    from app.agnes_provider import OpenAICompatibleProvider

    return OpenAICompatibleProvider(cfg)


def _with_constructed_prompt(req: dict) -> dict:
    """Phase2: 图片/视频节点按用户所选平台配置构造平台化提示词。

    仅对 image/video 生效 (文本节点走 BFF SSE, 不经此路径)。无平台配置/加载失败则原样返回。
    """
    if req.get("type") not in ("image", "video"):
        return req
    pc_id = req.get("platform_config_id")
    if not pc_id:
        return req
    try:
        pc = db.get_platform_config(pc_id)
    except Exception as e:  # noqa: BLE001
        print(f"[router] load platform_config {pc_id} failed: {e}")
        return req
    if not pc:
        return req
    constructed = prompt_layer.construct(req, pc)
    if constructed and constructed != req.get("prompt"):
        req = {**req, "prompt": constructed}
    return req


def route(req: dict) -> GenerationResult:
    """按 model 解析提供商并调用; 真实失败按策略决定回退 Mock 还是抛出。"""
    # 开发/联调极速开关: 命中的 type 直接走 MockProvider, 跳过 DB 解析与真实模型调用。
    # 用于把图像/视频生成压到 ~0.5s (真实 Agnes 单张 18~77s, 无法达到 1~3s)。
    if req.get("type") in settings.force_mock_types_set:
        print(f"[router] type '{req.get('type')}' in force_mock_types -> MockProvider (dev fast path)")
        return _mock.generate(req)

    model_id = req.get("model")
    cfg = None
    try:
        cfg = db.get_model_with_provider(model_id) if model_id else None
    except Exception as e:  # noqa: BLE001  DB 抖动不应让整条链路崩, 记录后按缺省处理
        print(f"[router] resolve model '{model_id}' failed: {e}")
        cfg = None

    # Phase2: 图片/视频节点按平台配置构造提示词 (mock / 真实 provider 共用同一构造结果)
    req = _with_constructed_prompt(req)

    # 解析不到模型 / 提供商停用 -> Mock 兜底 (仅联调) 或直接失败。
    if not cfg or not cfg.get("provider_enabled"):
        print(f"[router] model '{model_id}' -> unavailable (cfg={bool(cfg)}, enabled={cfg.get('provider_enabled') if cfg else None}), allow_mock={settings.allow_mock_fallback}")
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
            import traceback as _tb
            print(f"[router] !! generate() raised -> {type(e).__name__}: {e}")
            print(f"[router] traceback:\n{_tb.format_exc()}")
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
