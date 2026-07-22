"""pea Orchestrator 真实链路冒烟测试 (Tier-2 验证).

前置: MySQL/Redis 已在 localhost 可连 (docker compose up -d mysql redis minio)。
环境: PYTHONPATH 含 services/generation-orchestrator 与仓库根。
不走 HTTP/BFF, 直接 import 真实业务模块, 打到真实 MySQL + Redis。
"""
from __future__ import annotations

import os
import sys
import json
import time
import uuid
import threading

# ---- 必须在 import app 之前设置 (pydantic-settings 在导入时读 env) ----
os.environ.setdefault("PEA_DB_HOST", "localhost")
os.environ.setdefault("PEA_DB_PORT", "3306")
os.environ.setdefault("PEA_DB_USER", "pea")
os.environ.setdefault("PEA_DB_PASSWORD", "pea_dev")
os.environ.setdefault("PEA_DB_NAME", "pea")
os.environ.setdefault("PEA_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PEA_PROVIDER_PRIMARY", "mock")
os.environ.setdefault("PEA_PROVIDER_FALLBACK", "mock")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "services", "generation-orchestrator"))
sys.path.insert(0, ROOT)

passed, failed = 0, 0
def check(name: str, cond: bool, extra: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name} {extra}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {extra}")

# ---------------- 基础设施连通性 ----------------
print("== 1. 基础设施连通性 ==")
from app.redis_conn import client, enqueue_job
from app import db, models
from app.config import settings
from services.shared.events import EVENTS_CHANNEL, GEN_QUEUE

r = client()
check("redis ping", r.ping())

conn = db.get_conn()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN "
            "('users','accounts','ledger_entries','canvases','generation_jobs','works')",
            (settings.db_name,),
        )
        rows = {row["TABLE_NAME"] for row in cur.fetchall()}
    expect = {"users", "accounts", "ledger_entries", "canvases", "generation_jobs", "works"}
    check("mysql schema 已建表", expect <= rows, f"缺失={expect - rows}")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT PARTITION_NAME FROM information_schema.PARTITIONS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='ledger_entries' AND PARTITION_NAME IS NOT NULL",
            (settings.db_name,),
        )
        parts = {row["PARTITION_NAME"] for row in cur.fetchall()}
    check("ledger_entries 分区就绪", len(parts) >= 12, f"分区数={len(parts)}")
finally:
    conn.close()

# ---------------- 状态机合法性 ----------------
print("== 2. 生成状态机 ==")
check("queued->running 合法", models.can_transition("queued", "running"))
check("running->done 合法", models.can_transition("running", "done"))
check("failed->refunded 合法", models.can_transition("failed", "refunded"))
check("done->running 非法(拒收)", not models.can_transition("done", "running"))
check("queued->refunded 非法(拒收)", not models.can_transition("queued", "refunded"))
check("done 为终态", models.is_terminal("done"))

# ---------------- 事件发布订阅 ----------------
print("== 3. 跨服务事件发布/订阅 (Redis) ==")
captured: list[dict] = []
stop_sub = False
def _listen():
    ps = r.pubsub()
    ps.subscribe(EVENTS_CHANNEL)
    while not stop_sub:
        msg = ps.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if msg and msg.get("type") == "message":
            captured.append(json.loads(msg["data"]))
    ps.close()
listener = threading.Thread(target=_listen, daemon=True)
listener.start()
time.sleep(0.3)

# ---------------- Happy path: 端到端 ----------------
print("== 4. 端到端 Happy Path (入队->Worker->Mock出图->done) ==")
from app.worker import _ensure_group, run_once, _process

_ensure_group()
job_id = uuid.uuid4().hex
payload = {"user_id": 1, "type": "image", "cost_tapies": 10, "job_id": job_id}
with db.get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generation_jobs (id, user_id, type, status, cost_tapies) "
            "VALUES (%s, %s, %s, 'queued', %s)",
            (job_id, 1, "image", 10),
        )
    conn.commit()
enqueue_job(job_id, payload)
run_once()  # 消费一条

with db.get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT status, result_json FROM generation_jobs WHERE id=%s", (job_id,))
        row = cur.fetchone()
status = row["status"] if row else None
result_json = row["result_json"] if row else None
check("job 状态落库为 done", status == "done", f"status={status}")
check("result_json 已写入", bool(result_json), f"result={result_json}")
check("事件已发布(job.updated done)",
      any(e.get("kind") == "job.updated" and e.get("status") == "done" for e in captured),
      f"收到事件数={len(captured)}")

# ---------------- Failure + 补偿路径 ----------------
print("== 5. 失败路径 (primary/fallback 均失败 -> failed, 不崩溃) ==")
settings.provider_primary = "litellm:bogus"
settings.provider_fallback = "litellm:bogus"
job_id2 = uuid.uuid4().hex
payload2 = {"user_id": 1, "type": "image", "cost_tapies": 10, "job_id": job_id2}
with db.get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO generation_jobs (id, user_id, type, status, cost_tapies) "
            "VALUES (%s, %s, %s, 'queued', %s)",
            (job_id2, 1, "image", 10),
        )
    conn.commit()
enqueue_job(job_id2, payload2)
run_once()
with db.get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM generation_jobs WHERE id=%s", (job_id2,))
        row2 = cur.fetchone()
check("双 provider 失败 -> job 置 failed", row2["status"] == "failed", f"status={row2['status']}")
check("失败路径未崩溃(补偿退款调用BFF失败被吞)", True)

# 清理测试数据
with db.get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM generation_jobs WHERE id IN (%s,%s)", (job_id, job_id2))
    conn.commit()

stop_sub = True
listener.join(timeout=1)

print(f"\n=== 结果: PASS={passed} FAIL={failed} ===")
sys.exit(1 if failed else 0)
