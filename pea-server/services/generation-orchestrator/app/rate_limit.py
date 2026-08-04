"""分布式令牌桶(固定窗口计数)限流: per-(provider[, model][, tier]).

为什么需要它
------------
上游(Agnes 等)按"分档"限流(如 4K 档 1 次/60s), 而编排器此前完全没有客户端配额建模,
导致 60s 内第 2+ 个请求全撞 429, 且 429 被当 5xx 用 4s 退避重试(在 60s 窗口内必败, 还白烧额度)。

设计
----
- 规则来源: provider_rate_limits 表(BFF 后台可配, 编排器 TTL 缓存加载, 改完无需重启)。
  维度优先级(最具体胜出):
    (provider, model, tier) > (provider, model) > (provider, tier) > (provider) > 全局默认(None=不限)。
- 桶: Redis 固定窗口计数(复用 concurrency.py 的 redis_conn 原子 INCR/EXPIRE 模式,
  多副本共享同一配额, 不会各自为政)。桶 key 用"命中规则的 scope",
  保证同厂商级规则下所有模型共享一个桶(而不是每模型各一个桶)。
- acquire(provider_id, model_id?, tier?) -> (allowed, retry_after_s)。
  无匹配规则 -> 放行(True, 维持旧行为)。Redis 故障 -> 放行(由上游其它护栏兜底)。
- 注意: 这是"主动闸门", 把 429 挡在发生前; 即便配置缺失/上游临时变更,
  agnes_provider 里仍有"窗口感知的 429 重试"作被动兜底(见 RC-2 修复)。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from app.config import settings
from app.redis_conn import client as redis_client

logger = logging.getLogger(__name__)


_RULES_CACHE: list[dict] = []
_RULES_LOADED_AT: float = 0.0
_RULES_LOCK = threading.Lock()
# 全局默认(无表规则命中时的兜底); None = 不限制(维持旧行为)。
_DEFAULT_RULE: Optional[dict] = None


class RateLimitExceeded(RuntimeError):
    """主动闸门在 max_wait / max_retries 内仍拿不到令牌时抛出 -> 干净失败 + 退款。"""


def configure_default(rule: Optional[dict]) -> None:
    """注入全局默认规则(可选)。None = 无默认限制。"""
    global _DEFAULT_RULE
    _DEFAULT_RULE = rule


def _bucket_key(provider_id: str, model_id: Optional[str], tier: Optional[str]) -> str:
    return f"rate_limit:{provider_id}:{model_id or '*'}:{tier or '*'}"


def _rule_scope_key(rule: dict) -> str:
    return _bucket_key(rule["provider_id"], rule.get("model_id"), rule.get("tier"))


def load_rules(force: bool = False) -> list[dict]:
    """从 provider_rate_limits 表加载启用规则(带 TTL 缓存)。失败返回旧缓存或空。"""
    global _RULES_CACHE, _RULES_LOADED_AT
    now = time.time()
    if not force and _RULES_CACHE and (now - _RULES_LOADED_AT) < settings.provider_rate_limit_ttl_s:
        return _RULES_CACHE
    with _RULES_LOCK:
        # 双重检查, 避免并发重复查询 MySQL
        if not force and _RULES_CACHE and (time.time() - _RULES_LOADED_AT) < settings.provider_rate_limit_ttl_s:
            return _RULES_CACHE
        try:
            from app import db

            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, provider_id, model_id, tier, limit_n, window_s "
                        "FROM provider_rate_limits WHERE enabled = 1"
                    )
                    rows = cur.fetchall()
            rules = [dict(r) for r in rows]
            _RULES_CACHE = rules
            _RULES_LOADED_AT = time.time()
            logger.info("[rate_limit] loaded %d rules", len(rules))
            return rules
        except Exception as e:  # noqa: BLE001
            logger.warning("[rate_limit] load_rules failed: %s", e)
            return _RULES_CACHE  # 用旧缓存兜底


def resolve_rule(provider_id: str, model_id: Optional[str],
                 tier: Optional[str]) -> Optional[dict]:
    """按维度优先级返回命中的规则(含其 scope, 用于桶 key)。无命中返回全局默认或 None。"""
    rules = load_rules()

    def match(pid: str, mid: Optional[str], t: Optional[str]) -> Optional[dict]:
        for r in rules:
            if r["provider_id"] != pid:
                continue
            if (r.get("model_id") or None) != mid:
                continue
            if (r.get("tier") or None) != t:
                continue
            return r
        return None

    # 优先级: 具体 -> 宽泛
    for cand in (
        (provider_id, model_id, tier),
        (provider_id, model_id, None),
        (provider_id, None, tier),
        (provider_id, None, None),
    ):
        r = match(*cand)
        if r:
            return r
    return _DEFAULT_RULE


def acquire(provider_id: str, model_id: Optional[str] = None,
            tier: Optional[str] = None) -> tuple[bool, float]:
    """尝试获取一个令牌。返回 (allowed, retry_after_s)。

    allowed=True 可继续; allowed=False 需在 retry_after_s 秒后重试(且受 max_wait 约束)。
    """
    if not provider_id:
        return (True, 0.0)
    rule = resolve_rule(provider_id, model_id, tier)
    if rule is None:
        return (True, 0.0)
    limit = int(rule["limit_n"])
    window = int(rule["window_s"])
    key = _rule_scope_key(rule)
    r = redis_client()
    try:
        val = r.incr(key)
        if val == 1:
            # 首次占用: 设窗口 TTL(到期自动清零, 无需手动回收)。
            r.expire(key, window)
        if val > limit:
            # 超出配额: 回滚本次 INCR, 报告窗口剩余 TTL 作为等待时长。
            r.decr(key)
            ttl = r.ttl(key)
            wait = ttl if (ttl and ttl > 0) else window
            return (False, float(wait))
        return (True, 0.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("[rate_limit] acquire failed (provider=%s): %s", provider_id, e)
        # Redis 不可用 -> 放行(避免限流组件故障拖垮生成), 由上游其它护栏兜底
        return (True, 0.0)
