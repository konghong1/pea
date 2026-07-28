-- ---------------------------------------------------------------------------
-- T-FIX-ERROR-2026-07-28: generation_jobs 增加 error 列，持久化失败原因
-- ---------------------------------------------------------------------------
-- 背景: 之前失败详情 (如 "submit error: HTTPSConnectionPool Read timed out") 只
--       通过 publish_event 推 WS 一次, 没落库; 前端 GET /api/jobs/{id} 拿到
--       status=failed 但 error=null, 节点上只显示"生成失败"4 个字, 用户/客服
--       都没法自助排查。
-- 修复: 失败分支 (dispatcher.finalize_job) 把 error[:500] 写进新列;
--       api._row_to_dto 读出并返回; 前端失败卡可展示真实原因。
-- 幂等: IF NOT EXISTS 保护 (MySQL 8.0.29+ 支持)。
-- ---------------------------------------------------------------------------
ALTER TABLE generation_jobs
    ADD COLUMN IF NOT EXISTS error TEXT NULL AFTER result_json;
