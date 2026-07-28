"""自适应退避: 把固定 5s 轮询的 HTTP 负载砍 ~10 倍.

依据"已等待时长"动态拉长间隔 —— 快路径(多数任务 30s 内完成)保持秒级精度,
长任务降频到分钟级, 既不耽误正常完成, 也不空耗第三方连接。
"""
from __future__ import annotations


def next_interval(elapsed_s: float) -> int:
    """返回下一次轮询应等待的秒数.

    | 已等待      | 间隔   |
    |-------------|--------|
    | 0–30s       | 8s     |
    | 30–120s     | 25s    |
    | 120–300s    | 60s    |
    | 300s+       | 90s    |
    """
    if elapsed_s < 30:
        return 8
    if elapsed_s < 120:
        return 25
    if elapsed_s < 300:
        return 60
    return 90


def next_poll_delay_for(elapsed_s: float, floor: int = 5, ceiling: int = 90) -> int:
    """带上下限包装, 供配置化调用."""
    return max(floor, min(ceiling, next_interval(elapsed_s)))
