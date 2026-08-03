"""内置 provider 适配器包.

导入本包即触发各适配器模块的 ``@register_provider`` 装饰器执行, 从而把它们
登记进 ``app.async_core.provider_adapter.PROVIDER_REGISTRY``。

``build_adapter()`` 在工厂入口处**延迟导入**本包 (而非模块顶层 import),
以避免与 ``provider_adapter`` 形成循环导入 —— 适配器要继承 BaseProviderAdapter,
而工厂又要知道适配器, 这条环必须在函数体内打断。

新增厂商 = 在此目录加一个模块 + 在下面 import 一行, 不改工厂、不改分发逻辑。
"""
from __future__ import annotations

from app.providers import anthropic_compat, gemini, minimax, volcengine  # noqa: F401

__all__ = ["minimax", "anthropic_compat", "volcengine", "gemini"]
