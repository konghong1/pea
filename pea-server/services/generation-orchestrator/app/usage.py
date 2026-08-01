"""Phase3 token 计量钩子: 生成完成后把用量写入 usage_records.

这是"生成后钩子"的锚点 (对齐设计文档 PostGenerationHook): 核心生成调度(dispatch)流程不感知计量,
只在 DONE 后调一次 record_usage。后续要加计费公式 / 告警, 只改这里, 不动生成主流程。
"""
from __future__ import annotations

from typing import Any

from app import db


def record_usage(*, job_id: str | None, user_id: int, node_type: str, model: str | None,
                 provider: str | None, platform_config_id: str | None, usage: dict[str, Any]) -> None:
    """把一次生成的 token 用量落 usage_records。任何异常静默吞掉, 不影响主链路。"""
    try:
        db.insert_usage_record(
            user_id=user_id, job_id=job_id, node_type=node_type, model=model,
            provider=provider, platform_config_id=platform_config_id, usage=usage,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[usage] record failed job={job_id}: {e}")
