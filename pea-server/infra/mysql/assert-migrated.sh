#!/usr/bin/env bash
# =============================================================================
# pea Creative OS — 启动期 DDL 漂移自检 (T-OBS-04 防回归护栏)
#
# 背景: MySQL named volume 持久化后, /docker-entrypoint-initdb.d 下的
#       01-schema.sql 只在【首次建卷】时执行一次。之后源码里的 DDL 变更
#       (新增枚举值 / 新增列) 不会自动生效, 导致运行库与期望 schema 漂移,
#       典型症状: 注册 500 (ledger_entries.type 缺 'grant')。
#
# 本脚本在 bff / orchestrator 启动前一次性执行, 幂等地把已知漂移点修正回
# 源码基线。后续若再引入 DDL 变更, 在此追加对应断言即可, 无需手动 ALTER。
# =============================================================================
set -euo pipefail

HOST="${DB_HOST:-mysql}"
PORT="${DB_PORT:-3306}"
ROOT="${DB_ROOT_PASSWORD:-pea_root}"
DB="${DB_NAME:-pea}"
MYSQL_BIN="mysql -h $HOST -P $PORT -uroot -p$ROOT --connect-timeout=5"

echo "[assert-migrated] waiting for mysql to accept connections..."
for _ in $(seq 1 60); do
  if $MYSQL_BIN -e "SELECT 1" >/dev/null 2>&1; then
    echo "[assert-migrated] mysql is up."
    break
  fi
  sleep 1
done

# -----------------------------------------------------------------------------
# 断言 1: ledger_entries.type 必须包含 'grant' (开户赠金流水对账基准)
# 失败现象: 注册时 INSERT ... type='grant' 触发 500 "internal error"。
# -----------------------------------------------------------------------------
echo "[assert-migrated] checking ledger_entries.type enum..."
CURRENT=$($MYSQL_BIN -N -e \
  "SELECT COLUMN_TYPE FROM information_schema.COLUMNS \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='ledger_entries' AND COLUMN_NAME='type'" \
  2>/dev/null || true)

if [[ "$CURRENT" != *"grant"* ]]; then
  echo "[assert-migrated] FIX: ledger_entries.type missing 'grant' -> applying ALTER"
  $MYSQL_BIN -e \
    "ALTER TABLE $DB.ledger_entries \
     MODIFY COLUMN type ENUM('grant','preauth','confirm','refund') NOT NULL;"
  echo "[assert-migrated] FIX applied."
else
  echo "[assert-migrated] OK: ledger_entries.type = $CURRENT"
fi

echo "[assert-migrated] all assertions passed."
