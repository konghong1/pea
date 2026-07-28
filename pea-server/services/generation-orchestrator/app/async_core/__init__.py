"""异步完成层 (async_core).

把"任务提交"与"任务完成"彻底解耦:
- Dispatcher: 消费线程毫秒级快提交 + 入队句柄 + ACK, 不等待第三方渲染 (消除头阻塞).
- Completer: 独立后台线程, 按 next_poll_at 退避扫描到期句柄, 并发查状态.
- Webhook: 支持回调的厂商零轮询完成 (按 provider 各自密钥校验).
- 状态唯一真相源 = generation_task_handles 表 (崩溃安全 / 多副本乐观锁).
"""
from __future__ import annotations

from app.async_core import completer, concurrency, dispatcher, webhook
from app.async_core.dispatcher import dispatch, finalize_job
from app.async_core.completer import start as start_completer

__all__ = [
    "dispatcher",
    "completer",
    "webhook",
    "concurrency",
    "dispatch",
    "finalize_job",
    "start_completer",
]
