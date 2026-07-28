-- 异步完成层 DDL: ai_providers 扩展 + generation_task_handles
-- 执行顺序: 在 01-schema.sql 之后; 幂等 (已存在则跳过)。

-- 1) ai_providers 增加完成模式契约列
ALTER TABLE ai_providers
  ADD COLUMN completion_mode VARCHAR(16) NOT NULL DEFAULT 'poll' AFTER model_name,
  ADD COLUMN accepts_callback TINYINT NOT NULL DEFAULT 0 AFTER completion_mode,
  ADD COLUMN webhook_secret VARCHAR(255) NOT NULL DEFAULT '' AFTER accepts_callback;  -- 决策②: 每厂商各一把回调密钥

-- 2) 异步任务句柄表 (poll/webhook 调度的唯一真相源)
CREATE TABLE IF NOT EXISTS generation_task_handles (
  id                BIGINT AUTO_INCREMENT PRIMARY KEY,
  job_id            VARCHAR(36)  NOT NULL,
  user_id           INT          NOT NULL,
  provider          VARCHAR(64)  NOT NULL,
  completion_mode   VARCHAR(16)  NOT NULL,                 -- sync|poll|webhook
  provider_task_id  VARCHAR(128) NULL,
  provider_video_id VARCHAR(128) NULL,
  status_query      VARCHAR(512) NULL,                    -- 渲染后的状态查询地址
  phase             VARCHAR(16)  NOT NULL DEFAULT 'processing',
  raw_status        VARCHAR(32)  NULL,
  progress          INT          NULL,
  poll_attempts     INT          NOT NULL DEFAULT 0,
  last_poll_at      DATETIME(3)  NULL,
  next_poll_at      DATETIME(3)  NOT NULL,                -- 退避调度核心
  webhook_received_at DATETIME(3) NULL,
  claimed_by        VARCHAR(64)  NULL,                    -- 多副本乐观锁
  error             VARCHAR(512) NULL,
  created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uq_job (job_id),
  KEY idx_due (phase, next_poll_at),
  KEY idx_webhook (completion_mode, webhook_received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
