"""每用户并发令牌: Redis 原子计数 (替代 worker._in_flight 进程内 dict).

旧实现 _in_flight 是进程内 dict, 多 worker 副本下各自为政 -> 并发限制形同虚设
(每个实例只数自己, 用户实际能发起 limit * 副本数 个并发). 这里用 Redis INCR/DECR
做全局共享计数, 真正限得住单用户同时进行的任务数.

设计:
- acquire(user_id): INCR conc:{uid}; 首次占用设兜底 TTL (防异常未 release 永久泄漏);
  若 > limit -> DECR 回滚返回 False (拒绝); 否则 True.
- release(user_id): DECR conc:{uid} (下溢保护为 0).
并发上限取 settings.per_user_concurrency (=12, 决策④).
"""
from __future__ import annotations

import logging

from app.config import settings
from app.redis_conn import client

logger = logging.getLogger(__name__)


def _key(user_id: int) -> str:
    return f"conc:{user_id}"


def acquire(user_id: int) -> bool:
    """尝试占用一个并发名额. 成功 True, 达上限 False."""
    r = client()
    key = _key(user_id)
    limit = settings.per_user_concurrency
    try:
        val = r.incr(key)
        if val == 1:
            # 首次占用: 设兜底 TTL. 任务异常未 release 时自动恢复, 不永久卡用户.
            r.expire(key, settings.per_user_concurrency_ttl_s)
        if val > limit:
            r.decr(key)  # 回滚
            return False
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[concurrency] acquire failed uid=%s: %s", user_id, e)
        # Redis 不可用 -> 放行 (避免限流组件故障拖垮生成), 由上游其它护栏兜底
        return True


def release(user_id: int) -> None:
    """释放一个并发名额 (下溢保护)."""
    r = client()
    key = _key(user_id)
    try:
        cur = r.get(key)
        if cur is not None and int(cur) > 0:
            r.decr(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("[concurrency] release failed uid=%s: %s", user_id, e)
