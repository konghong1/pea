-- 004: 分档/分模型速率限制规则表 (RC-1 治本: 客户端配额建模)
-- 执行顺序: 在 003_job_error.sql 之后; 幂等 (已存在则跳过)。
-- 语义: 每个 (provider[, model][, tier]) 维度一组规则, limit_n 次 / window_s 秒。
--   tier 为图像分辨率档位 (4K/2K/...), NULL = 任意档; model_id NULL = 整家厂商适用。
-- 编排器启动时也会 CREATE TABLE IF NOT EXISTS 自建此表, 故 BFF/编排器部署顺序无关。

CREATE TABLE IF NOT EXISTS provider_rate_limits (
  id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
  provider_id VARCHAR(64)  NOT NULL,
  model_id    VARCHAR(64)  NULL,
  tier        VARCHAR(16)  NULL,                 -- 图像档位 '4K'/'2K'/...; NULL=任意档
  limit_n     INT          NOT NULL,            -- 每窗口允许请求数
  window_s    INT          NOT NULL,            -- 窗口秒数
  enabled     TINYINT      NOT NULL DEFAULT 1,
  created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_provider (provider_id),
  KEY idx_model (provider_id, model_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
