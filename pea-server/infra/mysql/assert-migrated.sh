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
# 必须显式指定 utf8mb4: 容器内 mysql 客户端默认 charset 可能不是 utf8mb4,
# 会导致含中文的种子 (提供商名/模型名/套餐名) 被按 latin1 解读再双编码成乱码。
MYSQL_BIN="mysql -h $HOST -P $PORT -uroot -p$ROOT --default-character-set=utf8mb4 --connect-timeout=5"

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

# -----------------------------------------------------------------------------
# 断言 6: 商业化底座 (提供商/模型/套餐/权益 + users 角色列)
# 背景: 持久卷首启后不会重跑 01-schema.sql 的新表/新列/种子。此处幂等自愈,
#       并把"旧版按用户隔离的 ai_providers(owner_id)"平滑重建为全局管理员级。
# -----------------------------------------------------------------------------

# 6.1 users 角色 / 权益列
add_col_if_missing users role            "role ENUM('user','admin') NOT NULL DEFAULT 'user' AFTER avatar_url"
add_col_if_missing users plan_level      "plan_level INT NOT NULL DEFAULT 0 AFTER role"
add_col_if_missing users plan_expires_at "plan_expires_at DATETIME(3) NULL AFTER plan_level"

# 6.2 旧版 ai_providers (含 owner_id) -> 重建为全局。旧数据仅为各用户的 mock 种子副本, 可安全丢弃。
LEGACY_PROV=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.COLUMNS \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='ai_providers' AND COLUMN_NAME='owner_id'" 2>/dev/null || echo 0)
if [[ "$LEGACY_PROV" != "0" ]]; then
  echo "[assert-migrated] FIX: legacy ai_providers(owner_id) detected -> rebuild as global"
  $MYSQL_BIN -e "DROP TABLE IF EXISTS $DB.ai_models; DROP TABLE IF EXISTS $DB.ai_providers;"
fi

# 6.3 建全局表 (幂等)
echo "[assert-migrated] ensuring commercialization tables..."
$MYSQL_BIN -e "
CREATE TABLE IF NOT EXISTS $DB.ai_providers (
    id VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    provider_type VARCHAR(40) NOT NULL DEFAULT 'openai-compatible',
    vendor VARCHAR(40) NOT NULL DEFAULT '',
    protocol VARCHAR(40) NOT NULL DEFAULT '',
    base_url VARCHAR(500) NOT NULL DEFAULT '',
    api_key VARCHAR(500) NOT NULL DEFAULT '',
    kind ENUM('image','video','text','audio','3d') NOT NULL DEFAULT 'image',
    enabled TINYINT NOT NULL DEFAULT 1,
    is_default TINYINT NOT NULL DEFAULT 0,
    config_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE IF NOT EXISTS $DB.ai_models (
    id VARCHAR(64) NOT NULL,
    provider_id VARCHAR(64) NOT NULL,
    model_name VARCHAR(200) NOT NULL,
    display_name VARCHAR(200) NOT NULL DEFAULT '',
    model_type ENUM('image','video','text','audio','3d') NOT NULL DEFAULT 'image',
    enabled TINYINT NOT NULL DEFAULT 1,
    is_default TINYINT NOT NULL DEFAULT 0,
    pricing_json JSON NULL,
    min_plan_level INT NOT NULL DEFAULT 0,
    params_schema_json JSON NULL,
    description VARCHAR(500) NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_models_provider (provider_id),
    KEY idx_models_type (model_type, enabled),
    CONSTRAINT fk_models_provider FOREIGN KEY (provider_id) REFERENCES $DB.ai_providers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE IF NOT EXISTS $DB.provider_remote_models (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    provider_id VARCHAR(64) NOT NULL,
    remote_model_id VARCHAR(255) NOT NULL,
    owned_by VARCHAR(255) NULL,
    model_type ENUM('image','video','text','audio','embedding','3d') NOT NULL DEFAULT 'text',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_provider_remote (provider_id, remote_model_id),
    KEY idx_remote_provider (provider_id),
    CONSTRAINT fk_remote_provider FOREIGN KEY (provider_id) REFERENCES $DB.ai_providers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS $DB.billing_plans (
    id VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    plan_level INT NOT NULL DEFAULT 1,
    price_cents INT NOT NULL DEFAULT 0,
    tapies INT NOT NULL DEFAULT 0,
    duration_days INT NOT NULL DEFAULT 30,
    enabled TINYINT NOT NULL DEFAULT 1,
    sort_order INT NOT NULL DEFAULT 0,
    features_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE IF NOT EXISTS $DB.user_plans (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    plan_id VARCHAR(64) NOT NULL,
    plan_level INT NOT NULL DEFAULT 1,
    tapies_granted INT NOT NULL DEFAULT 0,
    price_cents INT NOT NULL DEFAULT 0,
    purchased_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    expires_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    KEY idx_user_plans_user (user_id),
    CONSTRAINT fk_user_plans_user FOREIGN KEY (user_id) REFERENCES $DB.users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
"

# 6.3.1 ⚠️ 先确保 vendor / protocol 列存在 —— 必须在下方种子 INSERT 之前!
# 老卷的 ai_providers 由 01-schema.sql 首启时建表 (彼时还没有这两列), 这里
# CREATE TABLE IF NOT EXISTS 是 no-op, 若不在此提前补列, 下面的种子会因
# "Unknown column 'vendor'" 直接 1054 崩溃 (2026-08-03 dbmigrate exit 1 根因)。
# 新库 (CREATE TABLE 已含这两列) 此处为 no-op, 无副作用。
add_col_if_missing ai_providers vendor   "vendor VARCHAR(40) NOT NULL DEFAULT '' AFTER provider_type"
add_col_if_missing ai_providers protocol "protocol VARCHAR(40) NOT NULL DEFAULT '' AFTER vendor"

# 6.4 种子 (幂等)
echo "[assert-migrated] seeding admin / agnes / plans (idempotent)..."
$MYSQL_BIN -e "
INSERT INTO $DB.users (email, password_hash, display_name, role, plan_level)
VALUES ('admin@pea.ai', '\$2a\$10\$gjL30swN9Kg2.2mV7GmVBOCoe8XgHnLuVKSC.YkfjfqGZgEzlfemi', '平台管理员', 'admin', 999)
ON DUPLICATE KEY UPDATE role='admin', plan_level=999, display_name='平台管理员';

INSERT INTO $DB.accounts (user_id, balance, version)
SELECT id, 100000, 0 FROM $DB.users WHERE email='admin@pea.ai'
ON DUPLICATE KEY UPDATE balance=accounts.balance;

INSERT INTO $DB.ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
SELECT u.id, CONCAT('grant:', u.id), NULL, 'grant', 0, 100000, 100000
FROM $DB.users u
WHERE u.email='admin@pea.ai'
  AND NOT EXISTS (SELECT 1 FROM $DB.ledger_entries l WHERE l.txn_id = CONCAT('grant:', u.id));

INSERT INTO $DB.ai_providers (id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default)
VALUES ('agnes', 'Agnes AI', 'openai-compatible', 'agnes', 'openai-compatible', 'https://apihub.agnes-ai.com/v1',
        '', 'image', 1, 1)
ON DUPLICATE KEY UPDATE name=VALUES(name), provider_type=VALUES(provider_type),
    vendor=VALUES(vendor), protocol=VALUES(protocol),
    base_url=VALUES(base_url), api_key=COALESCE(NULLIF(VALUES(api_key),''), api_key), enabled=1;

INSERT INTO $DB.ai_models (id, provider_id, model_name, display_name, model_type, enabled, is_default, min_plan_level, pricing_json, params_schema_json, description, sort_order) VALUES
('agnes-image-2.0-flash', 'agnes', 'agnes-image-2.0-flash', 'Agnes 图像 2.0 Flash', 'image', 1, 1, 0,
  JSON_OBJECT('base', 10, 'tiers', JSON_OBJECT('size', JSON_OBJECT('1K', 0, '2K', 5, '4K', 20)), 'multiplier', 'n'),
  JSON_OBJECT('size', JSON_ARRAY('1K','2K','4K'), 'n', JSON_ARRAY(1,2,4)), '快速图像生成, 免费可用', 1),
('agnes-image-2.1-flash', 'agnes', 'agnes-image-2.1-flash', 'Agnes 图像 2.1 Flash', 'image', 1, 0, 1,
  JSON_OBJECT('base', 20, 'tiers', JSON_OBJECT('size', JSON_OBJECT('1K', 0, '2K', 10, '4K', 40)), 'multiplier', 'n'),
  JSON_OBJECT('size', JSON_ARRAY('1K','2K','4K'), 'n', JSON_ARRAY(1,2,4)), '高质量图像生成, 需基础套餐', 2),
('agnes-video-v2.0', 'agnes', 'agnes-video-v2.0', 'Agnes 视频 2.0', 'video', 1, 1, 2,
  JSON_OBJECT('base', 60, 'tiers', JSON_OBJECT('duration', JSON_OBJECT('5', 0, '10', 60)), 'multiplier', 'n'),
  JSON_OBJECT('duration', JSON_ARRAY(5,10), 'n', JSON_ARRAY(1)), '文生/图生视频, 需专业套餐', 3),
('agnes-2.5-pro-alpha', 'agnes', 'agnes-2.5-pro-alpha', 'Agnes 文本 2.5 Pro', 'text', 1, 1, 0,
  JSON_OBJECT('base', 2, 'tiers', JSON_OBJECT(), 'multiplier', 'n'), JSON_OBJECT(), '对话/文本生成', 4)
ON DUPLICATE KEY UPDATE model_name=VALUES(model_name), display_name=VALUES(display_name),
    model_type=VALUES(model_type), pricing_json=VALUES(pricing_json),
    params_schema_json=VALUES(params_schema_json), min_plan_level=VALUES(min_plan_level),
    description=VALUES(description);

INSERT INTO $DB.billing_plans (id, name, plan_level, price_cents, tapies, duration_days, enabled, sort_order, features_json) VALUES
('free',  '免费体验', 0,    0,  1000,  0,  1, 0, JSON_ARRAY('注册即送 1000 Tapies', '可用免费级模型')),
('basic', '基础套餐', 1, 1990,  5000, 30,  1, 1, JSON_ARRAY('到账 5000 Tapies', '解锁 2.1 Flash 高质量图像', '有效期 30 天')),
('pro',   '专业套餐', 2, 5990, 20000, 30,  1, 2, JSON_ARRAY('到账 20000 Tapies', '解锁全部图像 + 视频模型', '有效期 30 天'))
ON DUPLICATE KEY UPDATE name=VALUES(name), plan_level=VALUES(plan_level), price_cents=VALUES(price_cents),
    tapies=VALUES(tapies), duration_days=VALUES(duration_days), features_json=VALUES(features_json);
"
echo "[assert-migrated] commercialization base ready."

# 断言: 拓宽模型类型枚举以容纳 audio(音乐/语音) 与 3d (火山方舟 3D 生成)。
# 上面 189 起的大段 CREATE TABLE IF NOT EXISTS 对已存在的表是空操作, 不会修改枚举;
# 故此处显式 ALTER MODIFY, 让存量部署也能接纳 audio/3d 类型的模型与生成任务。
# 幂等: 重复执行对已是目标枚举的列无害 (MySQL 视为空操作/仅提示)。
$MYSQL_BIN -e "ALTER TABLE $DB.ai_providers MODIFY COLUMN kind ENUM('image','video','text','audio','3d') NOT NULL DEFAULT 'image';" 2>&1 | sed 's/^/  /'
$MYSQL_BIN -e "ALTER TABLE $DB.ai_models MODIFY COLUMN model_type ENUM('image','video','text','audio','3d') NOT NULL DEFAULT 'image';" 2>&1 | sed 's/^/  /'
$MYSQL_BIN -e "ALTER TABLE $DB.provider_remote_models MODIFY COLUMN model_type ENUM('image','video','text','audio','embedding','3d') NOT NULL DEFAULT 'text';" 2>&1 | sed 's/^/  /'
$MYSQL_BIN -e "ALTER TABLE $DB.generation_jobs MODIFY COLUMN type ENUM('image','video','text','audio','3d') NOT NULL;" 2>&1 | sed 's/^/  /'

# -----------------------------------------------------------------------------
# 断言 7: 节点聊天 Agent 所需 schema (Phase2 提示词构造层 / Phase3 token 计量)
#  - generation_jobs.usage_json 列
#  - platform_configs 表 (按用户所选平台配置构造提示词)
#  - usage_records 表 (token 用量审计)
# -----------------------------------------------------------------------------
echo "[assert-migrated] checking node-chat-agent schema..."
add_col_if_missing generation_jobs usage_json "usage_json JSON NULL AFTER result_json"

$MYSQL_BIN -e "
CREATE TABLE IF NOT EXISTS $DB.platform_configs (
    id VARCHAR(64) NOT NULL,
    owner_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(120) NOT NULL,
    platform VARCHAR(64) NOT NULL DEFAULT 'generic',
    kind ENUM('image','video') NOT NULL DEFAULT 'image',
    prompt_mode ENUM('plain','llm') NOT NULL DEFAULT 'plain',
    presets_json JSON NULL,
    expand_model VARCHAR(200) NULL,
    is_default TINYINT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_pc_owner (owner_id, kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS $DB.usage_records (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    job_id VARCHAR(36) NULL,
    node_type ENUM('text','image','video') NOT NULL,
    model VARCHAR(200) NULL,
    provider VARCHAR(120) NULL,
    platform_config_id VARCHAR(64) NULL,
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_ur_user (user_id, created_at),
    KEY idx_ur_job (job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
"
echo "[assert-migrated] node-chat-agent schema ready."

# 注: 必须在 CREATE TABLE platform_configs 之后才能 seed (否则 1146 表不存在)
echo "[assert-migrated] seeding platform_configs (idempotent)..."
$MYSQL_BIN -e "
INSERT INTO $DB.platform_configs (id, owner_id, name, platform, kind, prompt_mode, presets_json, expand_model, is_default)
SELECT 'pc_midjourney_img', u.id, 'Midjourney 风格', 'midjourney', 'image', 'plain',
       JSON_OBJECT('style_prefix','masterpiece, best quality, cinematic lighting','negative_prompt','blurry, lowres, deformed','aspect_ratio','1:1','quality','high'), NULL, 1
FROM $DB.users u WHERE u.email='admin@pea.ai'
ON DUPLICATE KEY UPDATE name=VALUES(name), presets_json=VALUES(presets_json);

INSERT INTO $DB.platform_configs (id, owner_id, name, platform, kind, prompt_mode, presets_json, expand_model, is_default)
SELECT 'pc_sora_video', u.id, 'Sora 电影感', 'sora', 'video', 'llm',
       JSON_OBJECT('style_prefix','cinematic, film grain, 35mm anamorphic','negative_prompt','','aspect_ratio','16:9','quality','high'), 'agnes-2.5-pro-alpha', 0
FROM $DB.users u WHERE u.email='admin@pea.ai'
ON DUPLICATE KEY UPDATE name=VALUES(name), presets_json=VALUES(presets_json), expand_model=VALUES(expand_model);
"
echo "[assert-migrated] platform_configs seeded."

# -----------------------------------------------------------------------------
# 断言 8: 素材库表 (asset_folders / assets) —— 左侧「文件/素材库」功能依赖
# -----------------------------------------------------------------------------
echo "[assert-migrated] checking asset library schema..."
AF_EXISTS=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.TABLES \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='asset_folders'" 2>/dev/null || echo 0)
if [[ "$AF_EXISTS" == "0" ]]; then
  echo "[assert-migrated] FIX: asset_folders missing -> CREATE"
  $MYSQL_BIN -e "
    CREATE TABLE $DB.asset_folders (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      owner_id BIGINT UNSIGNED NOT NULL,
      name VARCHAR(120) NOT NULL DEFAULT '新建文件夹',
      scope ENUM('personal','team') NOT NULL DEFAULT 'personal',
      parent_id BIGINT UNSIGNED NULL,
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id),
      KEY idx_af_owner (owner_id, scope),
      KEY idx_af_parent (parent_id),
      CONSTRAINT fk_af_owner FOREIGN KEY (owner_id) REFERENCES $DB.users (id),
      CONSTRAINT fk_af_parent FOREIGN KEY (parent_id) REFERENCES $DB.asset_folders (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
  "
fi

AS_EXISTS=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.TABLES \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='assets'" 2>/dev/null || echo 0)
if [[ "$AS_EXISTS" == "0" ]]; then
  echo "[assert-migrated] FIX: assets missing -> CREATE"
  $MYSQL_BIN -e "
    CREATE TABLE $DB.assets (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      owner_id BIGINT UNSIGNED NOT NULL,
      folder_id BIGINT UNSIGNED NULL,
      name VARCHAR(255) NOT NULL,
      object_key VARCHAR(1024) NOT NULL,
      content_type VARCHAR(120) NOT NULL DEFAULT '',
      size BIGINT UNSIGNED NOT NULL DEFAULT 0,
      scope ENUM('personal','team') NOT NULL DEFAULT 'personal',
      source ENUM('upload','generated') NOT NULL DEFAULT 'upload',
      is_favorite TINYINT NOT NULL DEFAULT 0,
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id),
      KEY idx_assets_owner (owner_id, scope, folder_id),
      KEY idx_assets_folder (folder_id),
      CONSTRAINT fk_assets_owner FOREIGN KEY (owner_id) REFERENCES $DB.users (id),
      CONSTRAINT fk_assets_folder FOREIGN KEY (folder_id) REFERENCES $DB.asset_folders (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
  "
fi

# -----------------------------------------------------------------------------
# 断言 9: 异步完成层 schema (迁移 002_async_handles / 003_job_error)
# 背景: async_core 引入 generation_task_handles 表 + ai_providers 完成模式列
#        (completion_mode/accepts_callback/webhook_secret) + generation_jobs.error 列;
#        这些迁移此前未纳入本自愈脚本, 导致运行库漂移 —— 典型症状:
#        - 视频 completer 每 tick 崩 (1146 Table 'generation_task_handles' doesn't exist)
#        - 图片 finalize 失败路径崩 (1054 Unknown column 'error' in field list) -> 图出不来
# 此处幂等自愈, 与 002/003 迁移保持一致。
# -----------------------------------------------------------------------------
echo "[assert-migrated] checking async completion layer schema..."
add_col_if_missing ai_providers completion_mode "completion_mode VARCHAR(16) NOT NULL DEFAULT 'poll' AFTER api_key"
add_col_if_missing ai_providers accepts_callback "accepts_callback TINYINT NOT NULL DEFAULT 0 AFTER completion_mode"
add_col_if_missing ai_providers webhook_secret  "webhook_secret VARCHAR(255) NOT NULL DEFAULT '' AFTER accepts_callback"
add_col_if_missing ai_providers external_ref_base_url "external_ref_base_url VARCHAR(512) NOT NULL DEFAULT '' AFTER webhook_secret"

HT_EXISTS=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.TABLES \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='generation_task_handles'" 2>/dev/null || echo 0)
if [[ "$HT_EXISTS" == "0" ]]; then
  echo "[assert-migrated] FIX: generation_task_handles missing -> CREATE"
  $MYSQL_BIN -e "
    CREATE TABLE $DB.generation_task_handles (
      id                BIGINT AUTO_INCREMENT PRIMARY KEY,
      job_id            VARCHAR(36)  NOT NULL,
      user_id           BIGINT       NOT NULL,
      provider          VARCHAR(64)  NOT NULL,
      completion_mode   VARCHAR(16)  NOT NULL,
      provider_task_id  VARCHAR(128) NULL,
      provider_video_id VARCHAR(128) NULL,
      status_query      VARCHAR(512) NULL,
      phase             VARCHAR(16)  NOT NULL DEFAULT 'processing',
      raw_status        VARCHAR(32)  NULL,
      progress          INT          NULL,
      poll_attempts     INT          NOT NULL DEFAULT 0,
      last_poll_at      DATETIME(3)  NULL,
      next_poll_at      DATETIME(3)  NOT NULL,
      webhook_received_at DATETIME(3) NULL,
      claimed_by        VARCHAR(64)  NULL,
      error             VARCHAR(512) NULL,
      created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      UNIQUE KEY uq_job (job_id),
      KEY idx_due (phase, next_poll_at),
      KEY idx_webhook (completion_mode, webhook_received_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
  "
fi

add_col_if_missing generation_jobs error "error TEXT NULL AFTER result_json"
echo "[assert-migrated] async completion layer schema ready."

# -----------------------------------------------------------------------------
# 断言 10: 支付域 schema (payment_qrcodes / payment_orders)
# 背景: 2026-08 关闭"用户自助购买直接到账"漏洞, 改为
#       下单 -> 扫收款码付款 -> 管理员确认到账 -> grantPlan() 发放。
# 这两张表是发放权益的唯一凭据, 缺表会让套餐页整条链路 500。
# named volume 已建的老库不会重跑 01-schema.sql, 故在此幂等补建。
# -----------------------------------------------------------------------------
echo "[assert-migrated] checking payment domain schema..."

QR_EXISTS=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.TABLES \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='payment_qrcodes'" 2>/dev/null || echo 0)
if [[ "$QR_EXISTS" == "0" ]]; then
  echo "[assert-migrated] FIX: payment_qrcodes missing -> CREATE"
  $MYSQL_BIN -e "
    CREATE TABLE $DB.payment_qrcodes (
      id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      channel    ENUM('wechat','alipay','other') NOT NULL DEFAULT 'wechat',
      label      VARCHAR(64) NOT NULL DEFAULT '',
      image_key  VARCHAR(512) NOT NULL,
      account_note VARCHAR(128) NOT NULL DEFAULT '',
      enabled    TINYINT NOT NULL DEFAULT 1,
      sort_order INT NOT NULL DEFAULT 0,
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id),
      KEY idx_qrcode_enabled (enabled, sort_order)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
  "
fi

ORD_EXISTS=$($MYSQL_BIN -N -e \
  "SELECT COUNT(*) FROM information_schema.TABLES \
   WHERE TABLE_SCHEMA='$DB' AND TABLE_NAME='payment_orders'" 2>/dev/null || echo 0)
if [[ "$ORD_EXISTS" == "0" ]]; then
  echo "[assert-migrated] FIX: payment_orders missing -> CREATE"
  $MYSQL_BIN -e "
    CREATE TABLE $DB.payment_orders (
      id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      order_no         VARCHAR(40)  NOT NULL,
      user_id          BIGINT UNSIGNED NOT NULL,
      plan_id          VARCHAR(64)  NOT NULL,
      plan_name        VARCHAR(120) NOT NULL DEFAULT '',
      plan_level       INT          NOT NULL DEFAULT 1,
      tapies           INT          NOT NULL DEFAULT 0,
      duration_days    INT          NOT NULL DEFAULT 30,
      amount_cents     INT          NOT NULL DEFAULT 0,
      pay_amount_cents INT          NOT NULL DEFAULT 0,
      provider         VARCHAR(32)  NOT NULL DEFAULT 'manual_qr',
      qrcode_id        BIGINT UNSIGNED NULL,
      status           ENUM('pending','submitted','paid','rejected','cancelled','expired')
                       NOT NULL DEFAULT 'pending',
      proof_key        VARCHAR(512) NULL,
      proof_note       VARCHAR(255) NULL,
      external_txn_id  VARCHAR(128) NULL,
      paid_amount_cents INT         NULL,
      reviewer_id      BIGINT UNSIGNED NULL,
      reviewed_at      DATETIME(3)  NULL,
      review_note      VARCHAR(255) NULL,
      granted          TINYINT      NOT NULL DEFAULT 0,
      expires_at       DATETIME(3)  NOT NULL,
      created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
      PRIMARY KEY (id),
      UNIQUE KEY uq_order_no (order_no),
      KEY idx_orders_user (user_id, created_at),
      KEY idx_orders_status (status, created_at),
      KEY idx_orders_amount (status, pay_amount_cents),
      CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES $DB.users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
  "
fi
echo "[assert-migrated] payment domain schema ready."

# -----------------------------------------------------------------------------
# 断言 11: MiniMax 全模型接入 (仅原生协议一条配置)
#
# ⚠️ 必须排在【断言 9】之后 —— 本段 seed 写 completion_mode / accepts_callback,
#    这些列由断言 9 补齐; 顺序颠倒会在旧库上报 1054 Unknown column。
#
#   minimax  协议=vendor-native, 厂商=minimax (原生 v2/v1)
#
# base_url 刻意不带 /v1: MiniMax 端点横跨 /v1/* 与 /v2/*, 由适配器按模型拼版本号。
# 参数档位均按上游报错原文实测校准 (H3 仅 2K / duration 4~15s / t2v 必填 ratio;
# Hailuo 仅 512P·768P·1080P)。
# -----------------------------------------------------------------------------
echo "[assert-migrated] seeding MiniMax providers & models (idempotent)..."
MM_KEY=''
$MYSQL_BIN -e "
INSERT INTO $DB.ai_providers
  (id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default, completion_mode, accepts_callback)
VALUES ('minimax', 'MiniMax 海螺', 'vendor-native', 'minimax', 'vendor-native', 'https://api.minimaxi.com', '$MM_KEY', 'video', 1, 0, 'poll', 0)
ON DUPLICATE KEY UPDATE name=VALUES(name), provider_type=VALUES(provider_type),
    vendor=VALUES(vendor), protocol=VALUES(protocol),
    base_url=VALUES(base_url), api_key=COALESCE(NULLIF(VALUES(api_key),''), api_key), enabled=1,
    completion_mode=VALUES(completion_mode);

# 清理已废弃的 MiniMax Anthropic 兼容入口 (单一厂商仅保留原生协议一条配置)。
# 先删子表模型, 再删父表 provider (避免外键约束报错)。
DELETE FROM $DB.ai_models WHERE provider_id='minimax-anthropic';
DELETE FROM $DB.ai_providers WHERE id='minimax-anthropic';

INSERT INTO $DB.ai_models (id, provider_id, model_name, display_name, model_type, enabled, is_default, min_plan_level, pricing_json, params_schema_json, description, sort_order) VALUES
('minimax-h3', 'minimax', 'MiniMax-H3', 'MiniMax 视频 H3 (2K)', 'video', 1, 0, 2,
  JSON_OBJECT('base', 150, 'tiers', JSON_OBJECT('duration', JSON_OBJECT('5', 0, '6', 20, '10', 140)), 'multiplier', 'n'),
  JSON_OBJECT('size', JSON_ARRAY('2K'), 'duration', JSON_ARRAY(5, 6, 10), 'n', JSON_ARRAY(1)),
  '旗舰视频模型, 原生 2K, 支持首帧/参考图, 需专业套餐', 11),
('minimax-hailuo-02', 'minimax', 'MiniMax-Hailuo-02', 'MiniMax 海螺视频 02', 'video', 1, 0, 1,
  JSON_OBJECT('base', 80, 'tiers', JSON_OBJECT('size', JSON_OBJECT('1K', 0, '2K', 40), 'duration', JSON_OBJECT('6', 0, '10', 60)), 'multiplier', 'n'),
  JSON_OBJECT('size', JSON_ARRAY('1K', '2K'), 'duration', JSON_ARRAY(6, 10), 'n', JSON_ARRAY(1)),
  '高性价比视频模型, 768P/1080P 可选, 支持首帧', 12),
('minimax-image-01', 'minimax', 'image-01', 'MiniMax 图像 01', 'image', 1, 0, 0,
  JSON_OBJECT('base', 8, 'tiers', JSON_OBJECT('size', JSON_OBJECT('1K', 0, '2K', 4, '4K', 16)), 'multiplier', 'n'),
  JSON_OBJECT('size', JSON_ARRAY('1K', '2K', '4K'), 'n', JSON_ARRAY(1, 2, 4)),
  '同步出图, 支持人物主体参考, 免费可用', 13),
('minimax-m2', 'minimax', 'MiniMax-M2', 'MiniMax M2 (推理)', 'text', 1, 0, 0,
  JSON_OBJECT('base', 2, 'tiers', JSON_OBJECT(), 'multiplier', 'n'), JSON_OBJECT(),
  '推理型文本模型, 思维链自动剥离', 14),
('minimax-m2-5', 'minimax', 'MiniMax-M2.5', 'MiniMax M2.5 (推理)', 'text', 1, 0, 1,
  JSON_OBJECT('base', 3, 'tiers', JSON_OBJECT(), 'multiplier', 'n'), JSON_OBJECT(),
  '更强推理型文本模型, 需基础套餐', 15)
ON DUPLICATE KEY UPDATE model_name=VALUES(model_name), display_name=VALUES(display_name),
    model_type=VALUES(model_type), pricing_json=VALUES(pricing_json),
    params_schema_json=VALUES(params_schema_json), min_plan_level=VALUES(min_plan_level),
    description=VALUES(description);
"
echo "[assert-migrated] MiniMax providers & models ready."

# -----------------------------------------------------------------------------
# 断言 12: ai_providers 新增 vendor / protocol 列 + 存量数据回填 (方案 A: 协议与厂商解耦)
#
# 背景: 原 provider_type 字段身兼两职 (协议族 + 厂商身份), 导致同一家厂商
#       支持多协议时要建多条 provider 记录 (如 minimax + minimax-anthropic)。
#       现拆分为正交的两个维度:
#         protocol = 协议族 (openai-compatible / anthropic-compatible / vendor-native)
#         vendor   = 厂商   (minimax / agnes / openai / anthropic / ''自定义)
#       provider_type 保留作向后兼容, 值始终与 protocol 同步写入。
#
# 存量迁移规则 (幂等):
#   provider_type='minimax'             -> protocol='vendor-native', vendor='minimax'
#   provider_type='openai-compatible'   -> protocol='openai-compatible', vendor 不变(通常为空或 agnes)
#   provider_type='anthropic-compatible'-> protocol='anthropic-compatible', vendor 不变
#   protocol 已非空的不动 (已在新库或历史上手动修正过)。
# -----------------------------------------------------------------------------
echo "[assert-migrated] backfilling vendor/protocol from legacy provider_type (idempotent)..."
$MYSQL_BIN -e "
  -- 原生厂商协议: 旧 'minimax' 类型 -> 拆为 protocol=vendor-native + vendor=minimax
  UPDATE $DB.ai_providers
     SET provider_type='vendor-native', protocol='vendor-native', vendor='minimax'
   WHERE provider_type='minimax' AND protocol='';
  -- 通用协议: protocol 直接取 provider_type 原值 (vendor 保持原状或为空)
  UPDATE $DB.ai_providers
     SET protocol=provider_type
   WHERE provider_type IN ('openai-compatible','anthropic-compatible')
     AND (protocol='' OR protocol IS NULL);
  -- Volcengine 火山方舟: 改为厂商原生协议 (vendor-native), 图像/视频走专用适配器
  -- (之前曾按 openai-compatible 注册, 但火山图像/视频端点非 OpenAI 兼容, 必须由
  --  @register_provider("vendor-native","volcengine") 驱动)。文本 chat 仍兼容 OpenAI。
  UPDATE $DB.ai_providers
     SET provider_type='vendor-native', protocol='vendor-native', vendor='volcengine'
   WHERE id='volcengine';
  -- 兜底: 任何残留空 protocol 归一到 openai-compatible (与 build_adapter 回退一致)
  UPDATE $DB.ai_providers
     SET protocol='openai-compatible'
   WHERE protocol='' OR protocol IS NULL;
  -- 彻底删除 mock provider (用户确认不再需要本地占位): 清掉其 provider 与模型
  DELETE FROM $DB.ai_models WHERE provider_id IN ('mock','mock-text');
  DELETE FROM $DB.ai_providers WHERE provider_type='mock' OR protocol='mock' OR id IN ('mock','mock-text');
"
echo "[assert-migrated] vendor/protocol backfill done."

echo "[assert-migrated] all assertions passed."
