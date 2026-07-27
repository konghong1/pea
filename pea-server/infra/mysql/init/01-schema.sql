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
    -- 权限角色: user(普通) / admin(可管理提供商/模型/定价/套餐)。管理员判定单一真源。
    role          ENUM('user','admin') NOT NULL DEFAULT 'user',
    -- 权益等级: 由已购套餐赋予, 与 ai_models.min_plan_level 比对做模型门槛控制。0=免费级。
    plan_level    INT NOT NULL DEFAULT 0,
    -- 当前权益到期时间; 过期后 plan_level 视为 0 (由 BFF 读取时判定, 无需定时任务)。
    plan_expires_at DATETIME(3) NULL,
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
    usage_json      JSON NULL,                     -- 本次生成的 token 用量 (由编排器回写, Phase3)
    cost_tapies     INT NOT NULL DEFAULT 0,
    idempotency_key VARCHAR(128) NULL,
    created_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_jobs_idem (idempotency_key),
    KEY idx_jobs_user (user_id),
    KEY idx_jobs_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- 节点聊天 Agent — 平台提示词配置 (Phase2: 图片/视频按用户所选平台构造提示词)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_configs (
    id              VARCHAR(64) NOT NULL,
    owner_id        BIGINT UNSIGNED NOT NULL,
    name            VARCHAR(120) NOT NULL,
    platform        VARCHAR(64) NOT NULL DEFAULT 'generic',   -- midjourney/dalle/sora/stable-diffusion/generic
    kind            ENUM('image','video') NOT NULL DEFAULT 'image',
    prompt_mode     ENUM('plain','llm') NOT NULL DEFAULT 'plain',  -- plain: 模板拼装; llm: 先调文本 LLM 扩写
    presets_json    JSON NULL,                                -- {style_prefix, negative_prompt, aspect_ratio, quality, extra}
    expand_model    VARCHAR(200) NULL,                        -- llm 模式扩写所用模型 (ai_models.id), 空则回退 plain
    is_default      TINYINT NOT NULL DEFAULT 0,
    created_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_pc_owner (owner_id, kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- 节点聊天 Agent — token 用量计量 (Phase3: 审计/统计, 不动计费公式)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usage_records (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id           BIGINT UNSIGNED NOT NULL,
    job_id            VARCHAR(36) NULL,
    node_type         ENUM('text','image','video') NOT NULL,
    model             VARCHAR(200) NULL,
    provider          VARCHAR(120) NULL,
    platform_config_id VARCHAR(64) NULL,
    input_tokens      INT NOT NULL DEFAULT 0,
    output_tokens     INT NOT NULL DEFAULT 0,
    total_tokens      INT NOT NULL DEFAULT 0,
    created_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_ur_user (user_id, created_at),
    KEY idx_ur_job (job_id)
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
-- E7 全局系统: AI Provider / Model / 套餐 / 权益 (管理员集中配置 + 动态计价)
--
-- 设计变更 (商业化底座): 原 ai_providers 按用户隔离已废弃。改为:
--   ai_providers   全局提供商 (含密钥/base_url), 仅 admin 可写。
--   ai_models      提供商下的具体模型, 带动态定价(pricing_json) + 门槛(min_plan_level)。
--   billing_plans  售卖套餐 (充值/权益等级)。
--   user_plans     用户购买记录 (赋予 plan_level + 到账 Tapies)。
-- 计费权威在 BFF: 受理生成时服务端按 模型 + 参数 算价, 忽略客户端传值。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_providers (
    id            VARCHAR(64)  NOT NULL,
    name          VARCHAR(120) NOT NULL,
    -- 适配器类型: openai-compatible (Agnes / OpenAI 兼容) / mock (本地占位, 不出网)
    provider_type VARCHAR(40)  NOT NULL DEFAULT 'openai-compatible',
    base_url      VARCHAR(500) NOT NULL DEFAULT '',
    -- 密钥: 明文存储于内网库, 仅内部服务读取; 对前端返回时必须脱敏 (见 providers.service)。
    api_key       VARCHAR(500) NOT NULL DEFAULT '',
    -- 主类目提示 (真实类型以 ai_models.model_type 为准)
    kind          ENUM('image','video','text','audio') NOT NULL DEFAULT 'image',
    enabled       TINYINT NOT NULL DEFAULT 1,
    is_default    TINYINT NOT NULL DEFAULT 0,
    config_json   JSON NULL,
    created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 具体模型: 一个提供商可挂多个模型。计价与门槛都落在模型粒度。
--
-- pricing_json 动态计价结构 (按参数计价, computeCost 见 BFF pricing 引擎):
--   {
--     "base": 10,                       -- 基础价 (无任何命中时的兜底)
--     "tiers": {                        -- 各参数维度的"加价档", 命中即在 base 上累加 delta
--       "size":     { "1K": 0, "2K": 5, "4K": 20 },
--       "duration": { "5": 0, "10": 40 }
--     },
--     "multiplier": "n"                 -- 数量倍率参数名 (最终价 = (base + Σdelta) * max(1, req[n]))
--   }
-- 规则: 命中档位累加, 未命中维度按 0 处理; 最终 max(1, 结果) 向下取整。
CREATE TABLE IF NOT EXISTS ai_models (
    id             VARCHAR(64)  NOT NULL,
    provider_id    VARCHAR(64)  NOT NULL,
    model_name     VARCHAR(200) NOT NULL,                 -- 传给 provider 的真实模型名
    display_name   VARCHAR(200) NOT NULL DEFAULT '',      -- 前端展示名
    model_type     ENUM('image','video','text') NOT NULL DEFAULT 'image',
    enabled        TINYINT NOT NULL DEFAULT 1,
    is_default     TINYINT NOT NULL DEFAULT 0,            -- 同类型唯一默认
    pricing_json   JSON NULL,                             -- 动态计价 (见上)
    min_plan_level INT  NOT NULL DEFAULT 0,               -- 门槛: 用户 plan_level >= 才可调用 (0=免费)
    params_schema_json JSON NULL,                         -- 前端参数选择器 schema (分辨率/时长/数量档位)
    description    VARCHAR(500) NOT NULL DEFAULT '',
    sort_order     INT NOT NULL DEFAULT 0,
    created_at     DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at     DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_models_provider (provider_id),
    KEY idx_models_type (model_type, enabled),
    CONSTRAINT fk_models_provider FOREIGN KEY (provider_id) REFERENCES ai_providers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 从 AI 提供商拉取的远端模型清单 (按类型持久化, 供「模型 & 定价」配置下拉选择)。
-- 与 ai_models 解耦: 此处是"提供商那边有哪些模型", ai_models 是"平台上架并计价的模型"。
-- model_type 词汇比 ai_models 更宽, 以反映提供商实际返回的各类模型。
CREATE TABLE IF NOT EXISTS provider_remote_models (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    provider_id      VARCHAR(64)  NOT NULL,
    remote_model_id  VARCHAR(255) NOT NULL,                 -- 传给 provider 的真实模型名
    owned_by         VARCHAR(255) NULL,
    model_type       ENUM('image','video','text','audio','embedding') NOT NULL DEFAULT 'text',
    created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_provider_remote (provider_id, remote_model_id),
    KEY idx_remote_provider (provider_id),
    CONSTRAINT fk_remote_provider FOREIGN KEY (provider_id) REFERENCES ai_providers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 售卖套餐: 购买后到账 tapies + 赋予 plan_level, 有效期 duration_days。
CREATE TABLE IF NOT EXISTS billing_plans (
    id            VARCHAR(64) NOT NULL,
    name          VARCHAR(120) NOT NULL,
    plan_level    INT NOT NULL DEFAULT 1,                 -- 权益等级 (模型门槛比对)
    price_cents   INT NOT NULL DEFAULT 0,                 -- 售价 (分, ¥)
    tapies        INT NOT NULL DEFAULT 0,                 -- 购买后到账 Tapies
    duration_days INT NOT NULL DEFAULT 30,                -- 有效期 (天), 0=永久
    enabled       TINYINT NOT NULL DEFAULT 1,
    sort_order    INT NOT NULL DEFAULT 0,
    features_json JSON NULL,                              -- 卖点列表 (前端展示)
    created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 用户购买记录 (审计 + 当前权益来源)。购买动作在事务内: 记录 + 加 Tapies(grant) + 更新 users.plan_level/expires。
CREATE TABLE IF NOT EXISTS user_plans (
    id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id        BIGINT UNSIGNED NOT NULL,
    plan_id        VARCHAR(64) NOT NULL,
    plan_level     INT NOT NULL DEFAULT 1,
    tapies_granted INT NOT NULL DEFAULT 0,
    price_cents    INT NOT NULL DEFAULT 0,
    purchased_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    expires_at     DATETIME(3) NULL,
    PRIMARY KEY (id),
    KEY idx_user_plans_user (user_id),
    CONSTRAINT fk_user_plans_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ---------------------------------------------------------------------------
-- 种子数据 (幂等: INSERT ... ON DUPLICATE KEY UPDATE)
-- ---------------------------------------------------------------------------

-- 管理员账号: admin@pea.ai / admin12345 (bcrypt hash, cost=10)。首启即可登录管理后台。
INSERT INTO users (email, password_hash, display_name, role, plan_level)
VALUES ('admin@pea.ai', '$2a$10$gjL30swN9Kg2.2mV7GmVBOCoe8XgHnLuVKSC.YkfjfqGZgEzlfemi', '平台管理员', 'admin', 999)
ON DUPLICATE KEY UPDATE role='admin', plan_level=999, display_name='平台管理员';

-- 管理员钱包 + 开户赠金流水 (对账基准), 幂等。
INSERT INTO accounts (user_id, balance, version)
SELECT id, 100000, 0 FROM users WHERE email='admin@pea.ai'
ON DUPLICATE KEY UPDATE balance=accounts.balance;
-- grant 流水唯一键为 (txn_id, created_at), ON DUPLICATE 无法跨次去重, 故用 NOT EXISTS 守卫。
INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
SELECT u.id, CONCAT('grant:', u.id), NULL, 'grant', 0, 100000, 100000
FROM users u
WHERE u.email='admin@pea.ai'
  AND NOT EXISTS (SELECT 1 FROM ledger_entries l WHERE l.txn_id = CONCAT('grant:', u.id));

-- Agnes AI 提供商 (真实调用)。
INSERT INTO ai_providers (id, name, provider_type, base_url, api_key, kind, enabled, is_default)
VALUES ('agnes', 'Agnes AI', 'openai-compatible', 'https://apihub.agnes-ai.com/v1',
        'sk-cTvTokWxT64boEgofyrgQf8QedwZNvlW5Dcbe1fz6JXsYtQE', 'image', 1, 1)
ON DUPLICATE KEY UPDATE
    name=VALUES(name), provider_type=VALUES(provider_type),
    base_url=VALUES(base_url), api_key=VALUES(api_key), enabled=1;

-- 本地 Mock 提供商 (离线/联调兜底, 不出网)。
INSERT INTO ai_providers (id, name, provider_type, base_url, api_key, kind, enabled, is_default)
VALUES ('mock', 'Mock 本地占位', 'mock', '', '', 'image', 1, 0)
ON DUPLICATE KEY UPDATE name=VALUES(name), provider_type=VALUES(provider_type);

-- Agnes 模型 (真实模型名, 已联网核对)。定价示例可在管理后台调整。
INSERT INTO ai_models (id, provider_id, model_name, display_name, model_type, enabled, is_default, min_plan_level, pricing_json, params_schema_json, description, sort_order) VALUES
('agnes-image-2.0-flash', 'agnes', 'agnes-image-2.0-flash', 'Agnes 图像 2.0 Flash', 'image', 1, 1, 0,
 JSON_OBJECT('base', 10, 'tiers', JSON_OBJECT('size', JSON_OBJECT('1K', 0, '2K', 5, '4K', 20)), 'multiplier', 'n'),
 JSON_OBJECT('size', JSON_ARRAY('1K','2K','4K'), 'n', JSON_ARRAY(1,2,4)),
 '快速图像生成, 免费可用', 1),
('agnes-image-2.1-flash', 'agnes', 'agnes-image-2.1-flash', 'Agnes 图像 2.1 Flash', 'image', 1, 0, 1,
 JSON_OBJECT('base', 20, 'tiers', JSON_OBJECT('size', JSON_OBJECT('1K', 0, '2K', 10, '4K', 40)), 'multiplier', 'n'),
 JSON_OBJECT('size', JSON_ARRAY('1K','2K','4K'), 'n', JSON_ARRAY(1,2,4)),
 '高质量图像生成, 需基础套餐', 2),
('agnes-video-v2.0', 'agnes', 'agnes-video-v2.0', 'Agnes 视频 2.0', 'video', 1, 1, 2,
 JSON_OBJECT('base', 60, 'tiers', JSON_OBJECT('duration', JSON_OBJECT('5', 0, '10', 60)), 'multiplier', 'n'),
 JSON_OBJECT('duration', JSON_ARRAY(5,10), 'n', JSON_ARRAY(1)),
 '文生/图生视频, 需专业套餐', 3),
('agnes-2.5-pro-alpha', 'agnes', 'agnes-2.5-pro-alpha', 'Agnes 文本 2.5 Pro', 'text', 1, 1, 0,
 JSON_OBJECT('base', 2, 'tiers', JSON_OBJECT(), 'multiplier', 'n'),
 JSON_OBJECT(),
 '对话/文本生成', 4)
ON DUPLICATE KEY UPDATE
    model_name=VALUES(model_name), display_name=VALUES(display_name),
    model_type=VALUES(model_type), pricing_json=VALUES(pricing_json),
    params_schema_json=VALUES(params_schema_json), min_plan_level=VALUES(min_plan_level),
    description=VALUES(description);

-- 售卖套餐 (三档)。
INSERT INTO billing_plans (id, name, plan_level, price_cents, tapies, duration_days, enabled, sort_order, features_json) VALUES
('free',  '免费体验', 0,    0,   1000,  0,  1, 0, JSON_ARRAY('注册即送 1000 Tapies', '可用免费级模型')),
('basic', '基础套餐', 1,  1990,  5000,  30, 1, 1, JSON_ARRAY('到账 5000 Tapies', '解锁 2.1 Flash 高质量图像', '有效期 30 天')),
('pro',   '专业套餐', 2,  5990, 20000,  30, 1, 2, JSON_ARRAY('到账 20000 Tapies', '解锁全部图像 + 视频模型', '有效期 30 天'))
ON DUPLICATE KEY UPDATE
    name=VALUES(name), plan_level=VALUES(plan_level), price_cents=VALUES(price_cents),
    tapies=VALUES(tapies), duration_days=VALUES(duration_days), features_json=VALUES(features_json);

-- ---------------------------------------------------------------------------
-- 视图: 账户总览 (方便顶栏/对账)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_user_balance AS
SELECT u.id AS user_id, u.email, u.display_name,
       COALESCE(a.balance, 0) AS balance,
       COALESCE(a.version, 0) AS version
FROM users u
LEFT JOIN accounts a ON a.user_id = u.id;
