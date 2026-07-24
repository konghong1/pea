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

# -----------------------------------------------------------------------------
# 断言 2: canvases.scope 必须为 personal|team (项目页范围筛选)
# 旧库缺该列会导致 GET /canvases?scope=team 直接抛 SQL 异常。
# -----------------------------------------------------------------------------
echo "[assert-migrated] checking canvases.scope..."
SCOPE_TYPE=$($MYSQL_BIN -N -e \
  "SELECT COLUMN_TYPE FROM information_schema.COLUMNS \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='canvases' AND COLUMN_NAME='scope'" \
  2>/dev/null || true)
if [[ -z "$SCOPE_TYPE" ]]; then
  echo "[assert-migrated] FIX: canvases.scope missing -> applying ALTER"
  $MYSQL_BIN -e \
    "ALTER TABLE $DB.canvases \
     ADD COLUMN scope ENUM('personal','team') NOT NULL DEFAULT 'personal' AFTER title;"
  echo "[assert-migrated] FIX applied (scope column added; idx added later after deleted_at exists)."
else
  echo "[assert-migrated] OK: canvases.scope = $SCOPE_TYPE"
fi

# -----------------------------------------------------------------------------
# 断言 3: canvases 必须有 folder_id/share_token/thumbnail_url/deleted_at
# -----------------------------------------------------------------------------
add_col_if_missing() {
  local table="$1" col="$2" ddl="$3"
  local exists
  exists=$($MYSQL_BIN -N -e \
    "SELECT COUNT(*) FROM information_schema.COLUMNS \
     WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='$table' AND COLUMN_NAME='$col'" \
    2>/dev/null || echo 0)
  if [[ "$exists" == "0" ]]; then
    echo "[assert-migrated] FIX: $table.$col missing -> $ddl"
    $MYSQL_BIN -e "ALTER TABLE $DB.$table ADD COLUMN $ddl;" 2>&1 | sed 's/^/  /'
    echo "[assert-migrated] FIX applied."
  else
    echo "[assert-migrated] OK: $table.$col exists"
  fi
}
add_col_if_missing canvases folder_id   "folder_id BIGINT UNSIGNED NULL AFTER scope"
add_col_if_missing canvases share_token "share_token VARCHAR(64) NULL AFTER folder_id"
add_col_if_missing canvases thumbnail_url "thumbnail_url VARCHAR(1024) NULL AFTER share_token"
add_col_if_missing canvases deleted_at  "deleted_at DATETIME(3) NULL AFTER version"

# share_token 唯一索引（旧库可能未建）
SHARE_IDX=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.STATISTICS \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='canvases' AND INDEX_NAME='uq_canvases_share'" \
  2>/dev/null || echo 0)
if [[ "$SHARE_IDX" == "0" ]]; then
  echo "[assert-migrated] FIX: adding uq_canvases_share"
  $MYSQL_BIN -e "ALTER TABLE $DB.canvases ADD UNIQUE KEY uq_canvases_share (share_token);"
fi

# 复合索引 (owner_id, scope, deleted_at) —— 必须在 deleted_at 列已加的前提下建
SCOPE_IDX=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.STATISTICS \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='canvases' AND INDEX_NAME='idx_canvases_scope'" \
  2>/dev/null || echo 0)
if [[ "$SCOPE_IDX" == "0" ]]; then
  echo "[assert-migrated] FIX: adding idx_canvases_scope"
  $MYSQL_BIN -e "ALTER TABLE $DB.canvases ADD KEY idx_canvases_scope (owner_id, scope, deleted_at);"
fi

# -----------------------------------------------------------------------------
# 断言 4: canvas_folders 表 (项目页"移动至文件夹"用)
# -----------------------------------------------------------------------------
CF_EXISTS=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.TABLES \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='canvas_folders'" 2>/dev/null || echo 0)
if [[ "$CF_EXISTS" == "0" ]]; then
  echo "[assert-migrated] FIX: canvas_folders missing -> CREATE"
  $MYSQL_BIN -e "
    CREATE TABLE $DB.canvas_folders (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      owner_id BIGINT UNSIGNED NOT NULL,
      name VARCHAR(120) NOT NULL DEFAULT '新建文件夹',
      scope ENUM('personal','team') NOT NULL DEFAULT 'personal',
      parent_id BIGINT UNSIGNED NULL,
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id),
      KEY idx_cf_owner (owner_id, scope),
      KEY idx_cf_parent (parent_id),
      CONSTRAINT fk_cf_owner FOREIGN KEY (owner_id) REFERENCES users (id),
      CONSTRAINT fk_cf_parent FOREIGN KEY (parent_id) REFERENCES canvas_folders (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
  "
fi

# canvases.folder_id -> canvas_folders.id 的 FK (旧库无)
CF_FK=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='canvases' AND CONSTRAINT_NAME='fk_canvases_folder'" \
  2>/dev/null || echo 0)
if [[ "$CF_FK" == "0" && "$CF_EXISTS" == "1" ]]; then
  echo "[assert-migrated] FIX: adding fk_canvases_folder"
  $MYSQL_BIN -e "ALTER TABLE $DB.canvases ADD CONSTRAINT fk_canvases_folder FOREIGN KEY (folder_id) REFERENCES canvas_folders (id) ON DELETE SET NULL;" 2>&1 | sed 's/^/  /'
fi

# -----------------------------------------------------------------------------
# 断言 5: canvas_versions.fk_cv_canvas 必须 ON DELETE CASCADE
# 失败现象: DELETE /canvases/:id 报 FK 约束 500。
# -----------------------------------------------------------------------------
CV_RULE=$($MYSQL_BIN -N -e \
  "SELECT DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS \
   WHERE CONSTRAINT_SCHEMA='$DB' AND TABLE_NAME='canvas_versions' AND CONSTRAINT_NAME='fk_cv_canvas'" \
  2>/dev/null || echo NONE)
if [[ "$CV_RULE" != "CASCADE" ]]; then
  echo "[assert-migrated] FIX: canvas_versions.fk_cv_canvas DELETE_RULE=$CV_RULE -> rebuilding as CASCADE"
  $MYSQL_BIN -e "ALTER TABLE $DB.canvas_versions DROP FOREIGN KEY fk_cv_canvas; \
                 ALTER TABLE $DB.canvas_versions ADD CONSTRAINT fk_cv_canvas FOREIGN KEY (canvas_id) REFERENCES canvases (id) ON DELETE CASCADE;" 2>&1 | sed 's/^/  /'
  echo "[assert-migrated] FIX applied."
else
  echo "[assert-migrated] OK: canvas_versions.fk_cv_canvas CASCADE"
fi

echo "[assert-migrated] all assertions passed."
