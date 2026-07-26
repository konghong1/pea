"""Smoke test: 节点聊天 Agent 后端 SSE 闭环 (mock 文本模型, 离线可跑)。

验证 (不依赖浏览器):
  - POST /chat/stream 返回 SSE, 含 meta(costTapies>0) + 多个 delta + done(text)。
  - 双记账本: 聊天预扣产生 ledger_entries.type='preauth' 一行。
  - Phase3: 若 mock 回传 usage, usage_records 应写入一行 (mock 无 usage 时仅告警)。

运行: 先 docker compose up (含 dbmigrate)。再 `python verify/smoke_node_chat_sse.py`。
退出码 0 = 通过。
"""
import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error

API = "http://localhost:4100"
EMAIL, PW = "verify@pea.ai", "password123"

MYSQL = [
    "docker", "exec", "pea-server-mysql-1", "mysql", "-upea", "-ppea_dev", "-N",
    "-e",
]


def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode()), e.code
        except Exception:
            return {"error": e.code}, e.code


def mysql_q(sql):
    p = subprocess.run(MYSQL + [sql], capture_output=True, text=True, timeout=30)
    return p.stdout.strip()


def main():
    fails = []
    notes = []

    tok = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})[0].get("token")
    if not tok:
        print("[FAIL] login failed"); return 1
    notes.append("login OK")

    # 离线 happy path: mock-text-1 设为默认文本模型
    r, code = api("PATCH", "/admin/models/mock-text-1", tok,
                  {"isDefault": True, "enabled": True})
    notes.append(f"set mock-text-1 default -> {code}")

    idem = f"smoke_{int(time.time()*1000)}"
    # 记录前水位
    before = mysql_q(
        "SELECT COUNT(*) FROM pea.ledger_entries le JOIN pea.users u ON u.id=le.user_id "
        f"WHERE u.email='{EMAIL}' AND le.type='preauth'")
    before = int(before or 0)

    # 发起 SSE
    body = json.dumps({
        "nodeId": "smoke-node-1", "kind": "text",
        "prompt": "用一句话介绍 pea Creative OS", "model": "mock-text-1",
        "idempotencyKey": idem,
    }).encode()
    req = urllib.request.Request(
        API + "/chat/stream", method="POST", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        print("[FAIL] /chat/stream HTTP", e.code, e.read().decode()[:300]); return 1

    # 解析 SSE
    meta = None
    deltas = []
    done = None
    for block in raw.split("\n\n"):
        ev = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if not ev or not data:
            continue
        try:
            payload = json.loads(data)
        except Exception:
            continue
        if ev == "meta":
            meta = payload
        elif ev == "delta":
            deltas.append(payload.get("text", ""))
        elif ev == "done":
            done = payload

    cost = (meta or {}).get("costTapies", 0)
    full = "".join(deltas)
    print(f"[check] meta.costTapies={cost}  deltas={len(deltas)}  done={'Y' if done else 'N'}  len={len(full)}")

    if not meta or cost <= 0:
        fails.append("meta 事件缺失或 costTapies<=0 (预扣未生效)")
    if len(deltas) == 0:
        fails.append("未收到任何 delta 事件")
    if not done or not (done.get("text") or "").strip():
        fails.append("done 事件缺失或无文本")
    else:
        notes.append("SSE 闭环成功: " + done["text"][:60].replace("\n", " "))

    # 双记账本: 预扣落库
    after = mysql_q(
        "SELECT COUNT(*) FROM pea.ledger_entries le JOIN pea.users u ON u.id=le.user_id "
        f"WHERE u.email='{EMAIL}' AND le.type='preauth'")
    after = int(after or 0)
    print(f"[check] ledger preauth: before={before} after={after}")
    if after <= before:
        fails.append("ledger_entries 未新增 preauth (双记账本预扣未落库)")
    else:
        notes.append("双记账本预扣落库 OK")

    # Phase3: usage_records (mock 可能无 usage, 仅告警)
    ur = mysql_q(
        "SELECT COUNT(*) FROM pea.usage_records ur JOIN pea.users u ON u.id=ur.user_id "
        f"WHERE u.email='{EMAIL}' AND ur.node_type='text' AND ur.created_at >= NOW() - INTERVAL 5 MINUTE")
    ur = int(ur or 0)
    print(f"[check] usage_records(text,近5min)={ur}")
    if ur == 0:
        notes.append("usage_records 无新增 (mock 文本未回传 usage, 非阻塞)")
    else:
        notes.append("Phase3 token 计量落库 OK")

    print("\n--- PASS 清单 ---")
    for n in notes:
        print("  [✓]", n)
    if fails:
        print("\n--- FAIL ---")
        for f in fails:
            print("  [✗]", f)
        return 1
    print("\n结果: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
