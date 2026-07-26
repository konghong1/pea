"""提示词构造层单元测试 (Phase2).

验证:
  - plain 模式: 用平台 presets 拼装 (style_prefix / negative / aspect / quality)。
  - 无平台配置: 原样返回聊天文本。
  - llm 模式无 expand_model: 自动回退 plain (不调 LLM, 链路不中断)。
  - 注册表扩展: 注册自定义 composer 后 construct 走自定义逻辑 (核心循环永不动)。
"""
from app.prompt_construction import (
    BasePromptComposer,
    PromptConstructionLayer,
    _assemble,
    INSTANCE,
)


def test_plain_assembles_presets():
    pc = {
        "prompt_mode": "plain",
        "presets_json": {
            "style_prefix": "masterpiece",
            "negative_prompt": "blurry",
            "aspect_ratio": "1:1",
            "quality": "high",
        },
    }
    out = INSTANCE.construct({"prompt": "一只猫", "type": "image"}, pc)
    assert "masterpiece" in out
    assert "一只猫" in out
    assert "negative prompt: blurry" in out
    assert "aspect ratio: 1:1" in out
    assert "quality: high" in out


def test_no_platform_config_returns_chat():
    assert INSTANCE.construct({"prompt": "hi"}, None) == "hi"


def test_llm_without_expand_model_falls_back_to_plain():
    pc = {"prompt_mode": "llm", "expand_model": None, "presets_json": {"style_prefix": "X"}}
    out = INSTANCE.construct({"prompt": "hi", "type": "image"}, pc)
    assert "X" in out and "hi" in out


def test_registry_extension():
    class CustomComposer(BasePromptComposer):
        mode = "custom"

        def compose(self, chat, presets, req, platform_config):
            return "CUSTOM:" + chat

    layer = PromptConstructionLayer()
    layer.register(CustomComposer())
    pc = {"prompt_mode": "custom", "presets_json": {}}
    assert layer.construct({"prompt": "z"}, pc) == "CUSTOM:z"


def test_assemble_order_preserves_prefix_before_chat():
    out = _assemble(
        "chat",
        {"style_prefix": "S", "negative_prompt": "N", "aspect_ratio": "16:9", "quality": "Q"},
    )
    assert out.index("S") < out.index("chat")
    assert out.index("chat") < out.index("negative prompt: N")
