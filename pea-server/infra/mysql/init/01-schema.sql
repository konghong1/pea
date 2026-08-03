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

-- ---------------------------------------------------------------------------
-- E4 素材库 (个人/团队双范围：图片、视频、音频、模型等生成资源与上传素材)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asset_folders (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_id    BIGINT UNSIGNED NOT NULL,
    name        VARCHAR(120) NOT NULL DEFAULT '新建文件夹',
    scope       ENUM('personal','team') NOT NULL DEFAULT 'personal',
    parent_id   BIGINT UNSIGNED NULL,
    created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_af_owner (owner_id, scope),
    KEY idx_af_parent (parent_id),
    CONSTRAINT fk_af_owner FOREIGN KEY (owner_id) REFERENCES users (id),
    CONSTRAINT fk_af_parent FOREIGN KEY (parent_id) REFERENCES asset_folders (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS assets (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_id     BIGINT UNSIGNED NOT NULL,
    folder_id    BIGINT UNSIGNED NULL,
    name         VARCHAR(255) NOT NULL,
    object_key   VARCHAR(1024) NOT NULL,
    content_type VARCHAR(120) NOT NULL DEFAULT '',
    size         BIGINT UNSIGNED NOT NULL DEFAULT 0,
    scope        ENUM('personal','team') NOT NULL DEFAULT 'personal',
    source       ENUM('upload','generated') NOT NULL DEFAULT 'upload',
    is_favorite  TINYINT NOT NULL DEFAULT 0,
    created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_assets_owner (owner_id, scope, folder_id),
    KEY idx_assets_folder (folder_id),
    CONSTRAINT fk_assets_owner FOREIGN KEY (owner_id) REFERENCES users (id),
    CONSTRAINT fk_assets_folder FOREIGN KEY (folder_id) REFERENCES asset_folders (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
    type            ENUM('image','video','text','audio','3d') NOT NULL,
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
    -- 协议族 (决定 HTTP body 格式, 与"厂商"正交):
    --   openai-compatible    OpenAI Chat Completions 兼容协议 (Agnes / OpenAI / 任何 OpenAI 兼容层)
    --   anthropic-compatible Anthropic Messages 协议 (官方或第三方兼容层)
    --   mock                 本地占位, 不出网
    --   vendor-native        厂商自有协议 (如 MiniMax 原生 v2 多模态 + v1 扁平 body, 通用格式盖不住)
    -- 注意: protocol 与 provider_type 同步写入同值; provider_type 仅作向后兼容保留。
    provider_type VARCHAR(40)  NOT NULL DEFAULT 'openai-compatible',
    -- 厂商标识 (与"协议"正交; 同一家厂商可能同时支持多种协议):
    --   minimax / agnes / openai / anthropic / '' (自定义)
    -- 仅当 protocol='vendor-native' 时必填, 用于路由到具体厂商适配器。
    vendor       VARCHAR(40)  NOT NULL DEFAULT '',
    -- 协议 (权威字段, 应用层应优先读此; 缺失时回退 provider_type 等价处理)
    protocol     VARCHAR(40)  NOT NULL DEFAULT '',
    base_url      VARCHAR(500) NOT NULL DEFAULT '',
    -- 密钥: 明文存储于内网库, 仅内部服务读取; 对前端返回时必须脱敏 (见 providers.service)。
    api_key       VARCHAR(500) NOT NULL DEFAULT '',
    -- 主类目提示 (真实类型以 ai_models.model_type 为准)
    kind          ENUM('image','video','text','audio','3d') NOT NULL DEFAULT 'image',
    enabled       TINYINT NOT NULL DEFAULT 1,
    is_default    TINYINT NOT NULL DEFAULT 0,
    config_json   JSON NULL,
    -- 每个 provider 各自的公网参考图基址(per-provider, 替代全局 PEA_EXTERNAL_REF_BASE_URL)。
    -- 外部模型(Agnes 等)下载参考图须公网可达; 为空则回退全局配置。不同模型可用不同隧道/域名,
    -- 避免"一个隧道死=全模型挂"的单点故障。
    external_ref_base_url VARCHAR(512) NOT NULL DEFAULT '',
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
    model_type     ENUM('image','video','text','audio','3d') NOT NULL DEFAULT 'image',
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
    model_type       ENUM('image','video','text','audio','embedding','3d') NOT NULL DEFAULT 'text',
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
-- 支付域 (2026-08): 下单 -> 付款 -> 确认到账 -> 发放权益
--
-- 设计要点:
--  1) 订单是"发放权益"的唯一凭据。plans.grantPlan() 只被订单审核通过 / 支付回调触发,
--     用户自助 purchase() 默认关闭 (PEA_ALLOW_SELF_PURCHASE=0), 杜绝自己给自己续费。
--  2) 套餐字段全部快照到订单行 (plan_name/plan_level/tapies/duration_days/amount_cents):
--     套餐改价或下架后, 旧订单仍按下单时的约定发放, 不会串价。
--  3) pay_amount_cents = 基准价 + 随机分位尾数(0~99分)。个人收款码收不到回调,
--     人工对账时靠这个唯一尾数把"收款通知里的金额"一一对应到订单, 避免同价撞单。
--     未过期的 pending/submitted 订单之间该金额唯一 (uq_pending_amount 保障)。
--  4) provider 区分 manual_qr (个人码 + 人工确认) 与 wechat_native (商户号自动回调),
--     两者写同一张表、走同一套状态机, 切换支付方式无需数据迁移。
-- ---------------------------------------------------------------------------

-- 收款码 (个人微信/支付宝码, 管理员上传, 前端支付弹窗展示)。
CREATE TABLE IF NOT EXISTS payment_qrcodes (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    channel    ENUM('wechat','alipay','other') NOT NULL DEFAULT 'wechat',
    label      VARCHAR(64) NOT NULL DEFAULT '',       -- 展示名, 如 "微信扫码"
    image_key  VARCHAR(512) NOT NULL,                 -- 对象存储 key (二维码图片)
    account_note VARCHAR(128) NOT NULL DEFAULT '',    -- 收款人备注, 便于用户核对
    enabled    TINYINT NOT NULL DEFAULT 1,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_qrcode_enabled (enabled, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 支付订单。状态机:
--   pending   下单待付款
--   submitted 用户已提交付款凭证, 等待管理员核对 (manual_qr 专有)
--   paid      已确认到账且权益已发放 (终态)
--   rejected  管理员驳回 (终态)
--   cancelled 用户主动取消 (终态)
--   expired   超时未支付, 由下单时的 expires_at 判定 (终态)
CREATE TABLE IF NOT EXISTS payment_orders (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no         VARCHAR(40)  NOT NULL,               -- 对外订单号
    user_id          BIGINT UNSIGNED NOT NULL,
    plan_id          VARCHAR(64)  NOT NULL,
    -- 套餐快照 (防改价串单)
    plan_name        VARCHAR(120) NOT NULL DEFAULT '',
    plan_level       INT          NOT NULL DEFAULT 1,
    tapies           INT          NOT NULL DEFAULT 0,
    duration_days    INT          NOT NULL DEFAULT 30,
    amount_cents     INT          NOT NULL DEFAULT 0,     -- 套餐标价 (分)
    pay_amount_cents INT          NOT NULL DEFAULT 0,     -- 实际应付 = 标价 + 随机尾数 (分)
    provider         VARCHAR(32)  NOT NULL DEFAULT 'manual_qr',
    qrcode_id        BIGINT UNSIGNED NULL,
    status           ENUM('pending','submitted','paid','rejected','cancelled','expired')
                     NOT NULL DEFAULT 'pending',
    -- 用户提交的付款凭证
    proof_key        VARCHAR(512) NULL,                   -- 付款截图对象 key
    proof_note       VARCHAR(255) NULL,                   -- 付款备注 (昵称/尾号)
    -- 支付网关回执 (wechat_native 路径填充)
    external_txn_id  VARCHAR(128) NULL,
    paid_amount_cents INT         NULL,                   -- 实收金额
    -- 审核轨迹
    reviewer_id      BIGINT UNSIGNED NULL,
    reviewed_at      DATETIME(3)  NULL,
    review_note      VARCHAR(255) NULL,
    granted          TINYINT      NOT NULL DEFAULT 0,     -- 权益是否已发放 (与 ledger txn_id 对账)
    expires_at       DATETIME(3)  NOT NULL,               -- 支付有效期
    created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_order_no (order_no),
    KEY idx_orders_user (user_id, created_at),
    KEY idx_orders_status (status, created_at),
    KEY idx_orders_amount (status, pay_amount_cents),     -- 按到账金额反查订单
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id)
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

-- Agnes AI 提供商 (真实调用)。协议=OpenAI 兼容, 厂商=agnes。
INSERT INTO ai_providers (id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default)
VALUES ('agnes', 'Agnes AI', 'openai-compatible', 'agnes', 'openai-compatible', 'https://apihub.agnes-ai.com/v1',
        '', 'image', 1, 1)
ON DUPLICATE KEY UPDATE
    name=VALUES(name), provider_type=VALUES(provider_type), vendor=VALUES(vendor),
    protocol=VALUES(protocol),
    base_url=VALUES(base_url), api_key=VALUES(api_key), enabled=1;

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

-- ---------------------------------------------------------------------------
-- MiniMax 提供商: 仅保留原生协议一条配置 (厂商=vendor-native 走私有端点)。
--
--   minimax  协议=vendor-native, 厂商=minimax —— 视频/图像/文本全覆盖
--           (适配器 app/providers/minimax.py, 注册 @register_provider("vendor-native","minimax"))
--
-- ⚠️ base_url 不带 /v1: MiniMax 端点分散在 /v1/* 与 /v2/* 两个版本下,
--    适配器按模型自行拼版本号。写死 /v1 会让 v2 视频 (MiniMax-H3) 拼错地址。
-- ---------------------------------------------------------------------------
INSERT INTO ai_providers (id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default)
VALUES ('minimax', 'MiniMax 海螺', 'vendor-native', 'minimax', 'vendor-native', 'https://api.minimaxi.com',
        '',
        'video', 1, 0)
ON DUPLICATE KEY UPDATE
    name=VALUES(name), provider_type=VALUES(provider_type), vendor=VALUES(vendor),
    protocol=VALUES(protocol),
    base_url=VALUES(base_url), api_key=VALUES(api_key), enabled=1;

-- ---------------------------------------------------------------------------
-- Volcengine 火山方舟 提供商: 厂商原生协议 (vendor-native), 厂商=volcengine。
--   图像(Seedream/SeedEdit)与视频(Seedance/Seaweed)走专用适配器
--   @register_provider("vendor-native","volcengine") (app/providers/volcengine.py),
--   与 MiniMax 同款模式; 文本 chat 走 /api/v3/chat/completions (OpenAI 兼容, 由该适配器一并覆盖)。
--   base_url 必须带 /api/v3: 火山方舟所有接口的版本前缀是 /api/v3
--   (chat/completions 在 /api/v3/chat/completions, 模型列表在 /api/v3/models,
--    图像在 /api/v3/images/generations, 视频在 /api/v3/contents/generations/tasks)。
--   编排器 _api_base 与 BFF normalizeModelsUrl / buildOpenAIChatUrl 已对该前缀做特殊处理,
--   原生适配器内部 _url() 也显式剥离/拼回 /api/v3, 写错前缀会 404。
-- ---------------------------------------------------------------------------
INSERT INTO ai_providers (id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default)
VALUES ('volcengine', '火山方舟 Volcengine', 'vendor-native', 'volcengine', 'vendor-native', 'https://ark.cn-beijing.volces.com/api/v3',
        '',
        'text', 1, 0)
ON DUPLICATE KEY UPDATE
    name=VALUES(name), provider_type=VALUES(provider_type), vendor=VALUES(vendor),
    protocol=VALUES(protocol),
    base_url=VALUES(base_url), api_key=VALUES(api_key), enabled=1;

-- ---------------------------------------------------------------------------
-- Google Gemini 提供商: 厂商原生协议 (vendor-native), 厂商=gemini。
--   文本(gemini-*)走 generateContent, 图像(gemini-*-image / nano-banana)走 generateContent
--   带 responseModalities=["IMAGE"], 视频(Veo)走 predictLongRunning, 均为 Google 自有协议,
--   非 OpenAI 兼容, 故用 vendor-native + 适配器 app/providers/gemini.py
--   @register_provider("vendor-native","gemini") 覆盖。
--
--   认证: 仅用 x-goog-api-key 头, **绝不能**再叠加 Authorization: Bearer —— 双头会 401
--   ("Expected OAuth 2 access token")。BFF authHeaders() 已为该厂商 return 单头。
--   base_url 可带或不带 /v1beta (适配器 _root() 与 BFF normalizeModelsUrl 都做了兜底)。
--   ⚠️ 该 key 初始无配额, 仅完成集成配置; 用户采购配额后 image/video 调用即可生效。
-- ---------------------------------------------------------------------------
INSERT INTO ai_providers (id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default)
VALUES ('gemini', 'Google Gemini', 'vendor-native', 'gemini', 'vendor-native', 'https://generativelanguage.googleapis.com/v1beta',
        '',
        'image', 1, 0)
ON DUPLICATE KEY UPDATE
    name=VALUES(name), provider_type=VALUES(provider_type), vendor=VALUES(vendor),
    protocol=VALUES(protocol),
    base_url=VALUES(base_url), api_key=VALUES(api_key), enabled=1;

-- MiniMax 模型 (参数档位均已按上游报错原文逐一实测校准, 见适配器注释)。
--   MiniMax-H3        v2 端点; resolution 仅 2K; duration 4~15s; 纯文生视频 ratio 必填
--   MiniMax-Hailuo-02 v1 端点; resolution 512P/768P/1080P; 两段式 file_id 取回
--   image-01          同步出图; 按 n 倍率计价
INSERT INTO ai_models (id, provider_id, model_name, display_name, model_type, enabled, is_default, min_plan_level, pricing_json, params_schema_json, description, sort_order) VALUES
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
