"""验证分档/分模型令牌桶 + 429 窗口解析。

使用**真实**的 app.rate_limit 代码, 仅用内存假 Redis 替换 redis_conn.client,
无需真实 Redis/MySQL 即可 e2e 跑通核心算法:
  1) 429 报文 / Retry-After 窗口解析 (_parse_rate_limit_wait_s)
  2) 令牌桶: 限流窗口内第 2+ 请求被拒(返回等待时长), 窗口重置后放行
  3) 维度隔离: (provider,model,tier) 桶独立于 (provider) 级桶(各自独立计数)

运行: python verify/verify_rate_limit.py
"""
import sys
import time

# 让 app 包可导入
sys.path.insert(0, r"D:\workspace\pea\pea-server\services\generation-orchestrator")
sys.path.insert(0, r"D:\workspace\pea\pea-server")


class FakeRedis:
    """最小实现 rate_limit 用到的 incr/expire/ttl/decr (固定窗口计数语义)。"""

    def __init__(self):
        self.data = {}
        self.expires = {}

    def incr(self, key):
        self.data[key] = self.data.get(key, 0) + 1
        return self.data[key]

    def decr(self, key):
        self.data[key] = self.data.get(key, 0) - 1
        return self.data[key]

    def expire(self, key, sec):
        self.expires[key] = time.time() + sec

    def ttl(self, key):
        if key in self.expires:
            left = self.expires[key] - time.time()
            return int(left) if left > 0 else -2
        return -1

    def get(self, key):
        return self.data.get(key)


fake = FakeRedis()

# 注入假 redis, 使 app.rate_limit 使用它(不连真实 Redis)
import app.redis_conn as rc

rc.client = lambda: fake

import app.rate_limit as rl

# 预热 app.async_core 包(init 顺序与运行时一致, 避免 agnes_provider 循环导入)
import app.async_core  # noqa: F401

# 跳过 DB 加载: 直接塞入缓存规则(模拟 BFF 后台已配置)
#  - 规则1: agnes 整家厂商 1 次/60s
#  - 规则2: agnes 模型 m1 的 4K 档 1 次/60s
rl._RULES_CACHE = [
    {"id": 1, "provider_id": "agnes", "model_id": None, "tier": None, "limit_n": 1, "window_s": 60},
    {"id": 2, "provider_id": "agnes", "model_id": "m1", "tier": "4K", "limit_n": 1, "window_s": 60},
]
rl._RULES_LOADED_AT = time.time()

# 429 窗口解析来源
import app.agnes_provider as ag


def fake_resp(status, body="", retry_after=None):
    class R:
        pass

    r = R()
    r.status_code = status
    r.text = body
    r.headers = {"Retry-After": retry_after} if retry_after else {}
    return r


fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ── 1) 429 窗口解析 ──
check("parse 'per 1 minute' -> 60",
      ag._parse_rate_limit_wait_s(
          fake_resp(429, "resolution rate limit exceeded: 4K tier allows 1 requests per 1 minute(s)"), 60) == 60)
check("parse 'per 30 second' -> 30",
      ag._parse_rate_limit_wait_s(fake_resp(429, "x per 30 second(s) y"), 60) == 30)
check("parse Retry-After 120 -> 120",
      ag._parse_rate_limit_wait_s(fake_resp(429, "", "120"), 60) == 120)
check("parse unknown body -> default 60",
      ag._parse_rate_limit_wait_s(fake_resp(429, "weird"), 60) == 60)

# ── 2) 令牌桶: provider 级 1/60s ──
fake.data.clear()
fake.expires.clear()
ok, _ = rl.acquire("agnes", None, None)
check("provider-level 1st acquire allowed", ok is True)
ok, wait = rl.acquire("agnes", None, None)
check("provider-level 2nd acquire blocked within window (wait<=60)", ok is False and wait <= 60)
# 模拟窗口到期(清空假 redis)
fake.data.clear()
fake.expires.clear()
ok, _ = rl.acquire("agnes", None, None)
check("provider-level acquire allowed after window reset", ok is True)

# ── 3) 维度隔离: (agnes,m1,4K) 桶 独立于 (agnes) 桶 ──
fake.data.clear()
fake.expires.clear()
ok1, _ = rl.acquire("agnes", "m1", "4K")
ok2, _ = rl.acquire("agnes", None, None)
check("model+tier bucket independent from provider bucket (both allowed 1st time)", ok1 and ok2)
ok1b, w1 = rl.acquire("agnes", "m1", "4K")
ok2b, w2 = rl.acquire("agnes", None, None)
check("both blocked on 2nd within window (separate buckets)", (not ok1b) and (not ok2b))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
