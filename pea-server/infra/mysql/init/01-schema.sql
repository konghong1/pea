-- ============================================================================
-- pea Creative OS — MySQL 8 Schema (idempotent)
-- 运行方式: docker 挂载本目录到 /docker-entrypoint-initdb.d，首次启动自动执行。
-- 可重复执行: 全部使用 CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS。
-- 锁定基线: ARCH-pea-Final.md §4；容量基线 10万用户/DAU2万/日生成~6k。
-- ============================================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ---------------------------------------------------------------------------
-- E1 身份与账户
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name  VARCHAR(120) NOT NULL DEFAULT '',
    avatar_url    VARCHAR(512) NULL,
    created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 积分钱包: balance 存整数 Tapies；version 乐观锁保证并发更新强一致
CREATE TABLE IF NOT EXISTS accounts (
    user_id    BIGINT UNSIGNED NOT NULL,
    balance    BIGINT NOT NULL DEFAULT 0,           -- 单位 Tapies，整数
    version    INT  UNSIGNED NOT NULL DEFAULT 0,     -- 乐观锁
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (user_id),
    CONSTRAINT fk_accounts_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 双记账本: 每一笔变动都落一行(借贷双方配对)。txn_id 唯一保证幂等(防重复扣费/退还)。
-- type 取值: grant(开户赠金, 对账基准) / preauth(预扣借方) / confirm(确认占位) / refund(退还贷方)。
-- 按月 RANGE 分区(成本/对账友好)；初始化覆盖 2026-01 ~ 2027-12，运维侧按需 ADD PARTITION。
CREATE TABLE IF NOT EXISTS ledger_entries (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id      BIGINT UNSIGNED NOT NULL,
    txn_id       VARCHAR(64) NOT NULL,               -- 幂等键 (jobId + ':' + action)
    job_id       VARCHAR(36) NULL,
    type         ENUM('grant','preauth','confirm','refund') NOT NULL,
    debit        BIGINT NOT NULL DEFAULT 0,          -- 扣减额
    credit       BIGINT NOT NULL DEFAULT 0,          -- 增加额
    balance_after BIGINT NOT NULL DEFAULT 0,         -- 该笔后余额(用于核对)
    created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id, created_at),
    -- 分区表约束: 唯一索引必须包含分区函数列(created_at)。txn_id 本身全局唯一, 加 created_at 不影响幂等语义。
    UNIQUE KEY uq_ledger_txn (txn_id, created_at),
    KEY idx_ledger_user (user_id),
    KEY idx_ledger_job (job_id)
)
ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
PARTITION BY RANGE (TO_DAYS(created_at)) (
    PARTITION p202601 VALUES LESS THAN (TO_DAYS('2026-02-01')),
    PARTITION p202602 VALUES LESS THAN (TO_DAYS('2026-03-01')),
    PARTITION p202603 VALUES LESS THAN (TO_DAYS('2026-04-01')),
    PARTITION p202604 VALUES LESS THAN (TO_DAYS('2026-05-01')),
    PARTITION p202605 VALUES LESS THAN (TO_DAYS('2026-06-01')),
    PARTITION p202606 VALUES LESS THAN (TO_DAYS('2026-07-01')),
    PARTITION p202607 VALUES LESS THAN (TO_DAYS('2026-08-01')),
    PARTITION p202608 VALUES LESS THAN (TO_DAYS('2026-09-01')),
    PARTITION p202609 VALUES LESS THAN (TO_DAYS('2026-10-01')),
    PARTITION p202610 VALUES LESS THAN (TO_DAYS('2026-11-01')),
    PARTITION p202611 VALUES LESS THAN (TO_DAYS('2026-12-01')),
    PARTITION p202612 VALUES LESS THAN (TO_DAYS('2027-01-01')),
    PARTITION p202701 VALUES LESS THAN (TO_DAYS('2027-02-01')),
    PARTITION p202702 VALUES LESS THAN (TO_DAYS('2027-03-01')),
    PARTITION p202703 VALUES LESS THAN (TO_DAYS('2027-04-01')),
    PARTITION p202704 VALUES LESS THAN (TO_DAYS('2027-05-01')),
    PARTITION p202705 VALUES LESS THAN (TO_DAYS('2027-06-01')),
    PARTITION p202706 VALUES LESS THAN (TO_DAYS('2027-07-01')),
    PARTITION p202707 VALUES LESS THAN (TO_DAYS('2027-08-01')),
    PARTITION p202708 VALUES LESS THAN (TO_DAYS('2027-09-01')),
    PARTITION p202709 VALUES LESS THAN (TO_DAYS('2027-10-01')),
    PARTITION p202710 VALUES LESS THAN (TO_DAYS('2027-11-01')),
    PARTITION p202711 VALUES LESS THAN (TO_DAYS('2027-12-01')),
    PARTITION p202712 VALUES LESS THAN (TO_DAYS('2028-01-01'))
);

-- ---------------------------------------------------------------------------
-- E3 画布 (JSON 列 + 生成列索引，PRD M1 痛点: 刷新即丢)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS canvases (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_id    BIGINT UNSIGNED NOT NULL,
    title       VARCHAR(255) NOT NULL DEFAULT 'Untitled',
    -- 范围: 个人空间 (root_only) / 团队空间 (scope=team)
    scope       ENUM('personal','team') NOT NULL DEFAULT 'personal',
    -- 文件夹 (canvas_folders.id)；NULL = 画布根目录
    folder_id   BIGINT UNSIGNED NULL,
    -- 分享令牌；生成后写入，可经公开端点只读访问
    share_token VARCHAR(64) NULL,
    -- 首屏缩略图 (可选；前端也可基于 graph 派生 CSS 渐变缩略)
    thumbnail_url VARCHAR(1024) NULL,
    graph_json  JSON NOT NULL,                        -- {nodes:[...], edges:[...]}
    version     INT UNSIGNED NOT NULL DEFAULT 1,      -- 乐观锁
    -- 软删除: 列表默认过滤 NULL；回收站恢复需另行设计
    deleted_at  DATETIME(3) NULL,
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_canvases_share (share_token),
    KEY idx_canvases_owner (owner_id),
    KEY idx_canvases_scope (owner_id, scope, deleted_at),
    KEY idx_canvases_folder (folder_id),
    CONSTRAINT fk_canvases_owner FOREIGN KEY (owner_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 生成列: 节点数(STORAGE, 可建索引，避免全表扫 JSON)
ALTER TABLE canvases
    ADD COLUMN node_count INT UNSIGNED AS (JSON_LENGTH(graph_json->'$.nodes')) STORED,
    ADD INDEX idx_canvases_node_count (node_count);

-- 画布文件夹: 支持个人/团队双范围；parent_id 自引用形成二级树
CREATE TABLE IF NOT EXISTS canvas_folders (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_id    BIGINT UNSIGNED NOT NULL,
    name        VARCHAR(120) NOT NULL DEFAULT '新建文件夹',
    scope       ENUM('personal','team') NOT NULL DEFAULT 'personal',
    parent_id   BIGINT UNSIGNED NULL,
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_cf_owner (owner_id, scope),
    KEY idx_cf_parent (parent_id),
    CONSTRAINT fk_cf_owner FOREIGN KEY (owner_id) REFERENCES users (id),
    CONSTRAINT fk_cf_parent FOREIGN KEY (parent_id) REFERENCES canvas_folders (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 补 FK: canvases.folder_id -> canvas_folders.id (ALTER 兼容旧库)
SET @fk_exists := (
  SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'canvases'
    AND CONSTRAINT_NAME = 'fk_canvases_folder'
);
SET @sql := IF(@fk_exists = 0,
  'ALTER TABLE canvases ADD CONSTRAINT fk_canvases_folder FOREIGN KEY (folder_id) REFERENCES canvas_folders (id) ON DELETE SET NULL',
  'SELECT 1');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

CREATE TABLE IF NOT EXISTS canvas_versions (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    canvas_id   BIGINT UNSIGNED NOT NULL,
    version     INT UNSIGNED NOT NULL,
    graph_json  JSON NOT NULL,
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_cv_canvas (canvas_id),
    CONSTRAINT fk_cv_canvas FOREIGN KEY (canvas_id) REFERENCES canvases (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- E2 生成管道 (orchestrator 拥有)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS generation_jobs (
    id              VARCHAR(36) NOT NULL,             -- jobId (uuid)
    user_id         BIGINT UNSIGNED NOT NULL,
    type            ENUM('image','video','text') NOT NULL,
    status          ENUM('queued','running','done','failed','refunded') NOT NULL DEFAULT 'queued',
    payload_json    JSON NULL,
    result_json     JSON NULL,
    cost_tapies     INT NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(128) NULL,
    created_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_jobs_idem (idempotency_key),
    KEY idx_jobs_user (user_id),
    KEY idx_jobs_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS generation_plans (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    job_id      VARCHAR(36) NOT NULL,
    steps_json  JSON NOT NULL,
    status      ENUM('draft','planned','generating','done','failed') NOT NULL DEFAULT 'draft',
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_plans_job (job_id),
    CONSTRAINT fk_plans_job FOREIGN KEY (job_id) REFERENCES generation_jobs (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- E6 电商套图 (本期搁置, 表结构保留以便 M1/M5 复用文件存储)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     BIGINT UNSIGNED NOT NULL,
    plan_id     BIGINT UNSIGNED NULL,
    title       VARCHAR(255) NOT NULL DEFAULT '',
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_products_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS product_images (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_id  BIGINT UNSIGNED NOT NULL,
    user_id     BIGINT UNSIGNED NOT NULL,
    image_url   VARCHAR(1024) NOT NULL,
    attrs_json  JSON NULL,
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_pi_product (product_id),
    CONSTRAINT fk_pi_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- E9 社区 / TapTV
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS works (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id         BIGINT UNSIGNED NOT NULL,
    media_urls      JSON NULL,
    caption         VARCHAR(2000) NOT NULL DEFAULT '',
    likes_count     INT NOT NULL DEFAULT 0,
    comments_count  INT NOT NULL DEFAULT 0,
    favorites_count INT NOT NULL DEFAULT 0,
    created_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_works_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS work_likes (
    work_id    BIGINT UNSIGNED NOT NULL,
    user_id    BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (work_id, user_id),
    CONSTRAINT fk_wl_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE,
    CONSTRAINT fk_wl_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS work_favorites (
    work_id    BIGINT UNSIGNED NOT NULL,
    user_id    BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (work_id, user_id),
    CONSTRAINT fk_wf_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE,
    CONSTRAINT fk_wf_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS work_comments (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    work_id    BIGINT UNSIGNED NOT NULL,
    user_id    BIGINT UNSIGNED NOT NULL,
    content    VARCHAR(1000) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_wc_work (work_id),
    CONSTRAINT fk_wc_work FOREIGN KEY (work_id) REFERENCES works (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- E7 全局系统: AI Provider 配置 (T-G-06 / FR-G7, 按用户隔离)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_providers (
    id          VARCHAR(64)  NOT NULL,
    owner_id    BIGINT UNSIGNED NOT NULL,
    name        VARCHAR(120) NOT NULL,
    kind        ENUM('image','video','text','audio') NOT NULL DEFAULT 'image',
    enabled     TINYINT NOT NULL DEFAULT 1,
    is_default  TINYINT NOT NULL DEFAULT 0,
    config_json JSON NULL,
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id, owner_id),
    KEY idx_providers_owner (owner_id),
    CONSTRAINT fk_providers_owner FOREIGN KEY (owner_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- 视图: 账户总览 (方便顶栏/对账)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_user_balance AS
SELECT u.id AS user_id, u.email, u.display_name,
       COALESCE(a.balance, 0) AS balance,
       COALESCE(a.version, 0) AS version
FROM users u
LEFT JOIN accounts a ON a.user_id = u.id;
