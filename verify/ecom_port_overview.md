# 电商套图模块移植 + 生成轮询 500 根治（2026-07-25）

## 一、电商套图模块移植（前端，已完成并验证）

按需求从 `C:\workspace\ai-agent` 的 `EcommerceGallery` 移植电商套图到当前 pea 项目，并适配 pea 现有 AI 提供商模型选择机制，样式对齐 pea 设计令牌。

**新增文件**（`pea-server/web/src/components/ecom/`）：
- `EcomGallery.tsx` — 主页面，4 步流程：上传产品图 → 填写卖点/市场 → AI 策划出图规划（抽屉）→ 一键生成套图；含预览/重作/提示词弹窗/模板保存。
- `ModelPicker.tsx` — 模型选择，数据源为 pea 当前 AI 提供商模型列表（`/models/available`），标注默认/参考价/未解锁权益等级。
- `ecomApi.ts` — 本地服务层：模型加载走 `listAvailableModels('image')`；生成走 pea 真实后端 `acceptGenerationJob` + 轮询 `/generation/jobs/:jobId`；类型配置/草稿/模板用前端状态 + localStorage 兜底。
- `ecom.css` — 对齐 pea 设计令牌，深色靠 `.dark`。
- `pages/Ecom.tsx` — 改为渲染 `EcomGallery`。

**验证**：`verify/verify_ecom_port.py` 打生产 `:8088`，**13/13 全绿**（Q1 渲染 / Q2 模型下拉含真实 Agnes 模型 / Q3 策划 / Q4 生成提交 / Q5 0 console error）。

## 二、顺带根治的真问题：生成轮询 500（后端，非移植缺陷）

移植后复验发现 Q5 报 500。排查链路：

- 浏览器 console 500 → 抓 URL 定位到 `GET /generation/jobs/:jobId`。
- 编排器侧该接口实际返回 **404**（axios 非 2xx 抛异常 → BFF 透传为 500）；而该行在 MySQL 中确存在。
- 编排器日志同一 jobId **间歇 200/404** → 连接池卫生缺陷。

**根因**：`services/generation-orchestrator/app/db.py` 自研连接池 `_Conn.__exit__` 归还连接前**未 rollback 未提交事务**。MySQL `autocommit=False` + REPEATABLE READ 下，worker 的 `SELECT..FOR UPDATE` 与 `get_model_with_provider()` 裸 SELECT 会开启事务并固定快照；异常路径把带旧快照的连接放回池中 → 后续 `get_job` 的 SELECT 看不到新插入的行 → 误报 404 → BFF 500。

**修复**：`_Conn.__exit__` 归还前 `self._raw.rollback()`（已 commit 的事务 rollback 为 no-op，安全）。已 `docker compose up -d --build generation-orchestrator` 烤入镜像。复验稳定 200、验证 13/13 / 0 console error。

## 三、遗留（非移植/修复范围，后端外部依赖）

编排器 worker 调 Agnes 出图；本沙箱无外网到 Agnes，且 `allow_mock_fallback=False`（生产护栏）不可擅自开启，故任务最终 failed/无图。属后端外部依赖，非本次移植或 500 修复的问题。本地联调出图可临时 `PEA_ALLOW_MOCK_FALLBACK=true`（仅离线）。
