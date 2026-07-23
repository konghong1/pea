#!/usr/bin/env python3
"""
每日对账脚本 (T-ACC-04 / ARCH D12 R4).

比对每个用户的 ledger_entries 流水汇总 (SUM(credit) - SUM(debit))
与 accounts.balance 是否一致。不一致即输出差异并退出码 1, 供 cron/告警捕获。

运行:
  export PEA_DB_HOST=... PEA_DB_USER=... PEA_DB_PASSWORD=... PEA_DB_NAME=pea
  python scripts/reconcile_ledger.py

说明: 真正的强一致由事务 + 行锁保证; 本脚本是**最后兜底**,
捕捉因补偿退款失败 (BFF 抖动) 等极端情况导致的余额漂移。
"""
from __future__ import annotations

import os
import sys

import pymysql


def get_conn():
    return pymysql.connect(
        host=os.environ.get("PEA_DB_HOST", "mysql"),
        port=int(os.environ.get("PEA_DB_PORT", "3306")),
        user=os.environ.get("PEA_DB_USER", "pea"),
        password=os.environ.get("PEA_DB_PASSWORD", "pea_dev"),
        database=os.environ.get("PEA_DB_NAME", "pea"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def reconcile(conn) -> list[dict]:
    mismatches: list[dict] = []
    with conn.cursor() as cur:
        # 账户当前余额
        cur.execute("SELECT user_id, balance FROM accounts")
        balances = {row["user_id"]: row["balance"] for row in cur.fetchall()}

        # 流水汇总 (含 grant 开户赠金)
        cur.execute(
            "SELECT user_id, COALESCE(SUM(credit),0) - COALESCE(SUM(debit),0) AS computed "
            "FROM ledger_entries GROUP BY user_id"
        )
        computed = {row["user_id"]: row["computed"] for row in cur.fetchall()}

    all_users = set(balances) | set(computed)
    for uid in sorted(all_users):
        bal = balances.get(uid, 0)
        comp = computed.get(uid, 0)
        if bal != comp:
            mismatches.append({"user_id": uid, "balance": bal, "computed_from_ledger": comp, "diff": bal - comp})
    return mismatches


def main() -> int:
    conn = get_conn()
    try:
        mismatches = reconcile(conn)
    finally:
        conn.close()

    if not mismatches:
        print("[reconcile] OK: 所有账户余额与流水一致")
        return 0

    print(f"[reconcile] 发现 {len(mismatches)} 个账户余额漂移:")
    for m in mismatches:
        print(f"  user_id={m['user_id']} balance={m['balance']} "
              f"ledger_computed={m['computed_from_ledger']} diff={m['diff']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
