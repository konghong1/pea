"""pea BFF 真实链路 e2e (Tier-3 验证). 前置: BFF(:4000)+Orchestrator(:8000)+MySQL+Redis 已起.

覆盖 E1 积分双记账本 + E2 生成受理链路:
  注册赠 1000 -> 提交生成预扣 10 -> 余额 990 -> worker 消费至 done
  -> 内部退款幂等(不双退) -> 余额回 1000 -> ledger 双记账本可追溯.
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error

BASE = "http://localhost:4000"
INTERNAL_TOKEN = "dev-token"

passed = 0
failed = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name} {extra}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {extra}")


def req(method: str, path: str, body: dict | None = None, token: str | None = None,
         internal: bool = False) -> tuple[int, dict]:
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if internal:
        r.add_header("X-Service-Token", INTERNAL_TOKEN)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


print("== 1. 注册 -> 账户自动创建(赠 free Tapies) ==")
email = f"qa_{int(time.time())}@pea.dev"
st, reg = req("POST", "/auth/register", {"email": email, "password": "pw123456", "displayName": "QA"})
token = reg.get("token", "")
uid = reg.get("user", {}).get("id")
check("register 返回 token+user", st == 201 and bool(token) and uid is not None, f"uid={uid}")

print("== 2. 初始余额 = 1000 ==")
st, bal = req("GET", "/billing/balance", token=token)
b0 = bal.get("balance")
check("初始余额=1000", b0 == 1000, f"got {b0}")

print("== 3. 提交生成 -> 预扣 10 -> 余额 990 ==")
st, acc = req("POST", "/generation/jobs", {"type": "image", "prompt": "premium shot", "costTapies": 10}, token=token)
job_id = acc.get("jobId")
check("generation accept 返回 jobId", st == 201 and bool(job_id), f"job={job_id}")
time.sleep(1.0)
st, bal2 = req("GET", "/billing/balance", token=token)
b1 = bal2.get("balance")
check("预扣后余额=990", b1 == 990, f"got {b1}")
# ledger 应已记 preauth
st, led = req("GET", "/billing/ledger", token=token)
led_types = [e.get("type") for e in led] if isinstance(led, list) else led.get("ledger", [])
check("ledger 含 preauth 分录", "preauth" in led_types, f"types={led_types[:5]}")

print("== 4. worker(编排器进程内) 消费 -> job 终态 ==")
done = False
for _ in range(10):
    st, job = req("GET", f"/generation/jobs/{job_id}", token=token)
    if job.get("status") == "done":
        done = True
        break
    time.sleep(0.5)
check("job 跑到 done (mock 出图)", done, f"status={job.get('status')}")

print("== 5. 内部退款幂等(模拟 orchestrator 补偿) ==")
st, ref1 = req("POST", "/internal/billing/refund",
               {"userId": uid, "amount": 10, "txnId": "e2e-refund-1", "jobId": job_id}, internal=True)
check("refund 第一次成功 (ok=true)", ref1.get("ok") is True, f"{ref1}")
st, bal3 = req("GET", "/billing/balance", token=token)
b2 = bal3.get("balance")
check("退款后余额回 1000", b2 == 1000, f"got {b2}")
st, ref2 = req("POST", "/internal/billing/refund",
               {"userId": uid, "amount": 10, "txnId": "e2e-refund-1", "jobId": job_id}, internal=True)
st, bal4 = req("GET", "/billing/balance", token=token)
b3 = bal4.get("balance")
check("重复退款幂等: 余额仍 1000 (未双退)", b3 == 1000, f"got {b3}")

print("== 6. 双记账本完整可追溯 ==")
st, led = req("GET", "/billing/ledger", token=token)
types = [e.get("type") for e in led] if isinstance(led, list) else led.get("ledger", [])
check("ledger 同时含 preauth + refund", "preauth" in types and "refund" in types, f"types={types[:8]}")

print(f"\n=== e2e 结果: PASS={passed} FAIL={failed} ===")
raise SystemExit(1 if failed else 0)
