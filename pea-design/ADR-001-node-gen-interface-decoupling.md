# ADR-001: 节点图片/视频生成与电商套图接口解耦

## Status
Accepted (2026-07-26)

## Context
节点（Canvas 节点）的图片/视频生成，与「电商套图」批量生成，原本共用同一个受理端点
`POST /generation/jobs`（BFF `GenerationController.accept` → `GenerationService.accept`）。

两个问题因此产生：
1. **耦合点不清**：两类调用方在 BFF 边界完全相同，无法独立演进参数拼装策略。
2. **语义混淆**：`/generation/jobs` 携带 `platformConfigId`（提示词构造层），而节点图片/视频
   的"平台配置"实为**用户自己在节点 UI 勾选的比例/分辨率**（节点前端自行拼成 width/height/size），
   并不走 `platform_configs` 提示词构造层。两者"底层调同一模型，但拼接参数方式不同"。

用户明确要求：节点图片/视频生成**不要**和电商套图用同一个接口。

## Decision
新增**节点专用端点** `POST /generation/node`，与电商套图的 `POST /generation/jobs` 在 API 边界完全分离：

- **节点侧 `AcceptNodeGenerationDto`**：不含 `platformConfigId`。节点前端已用比例/分辨率 UI 拼好
  `params.width/height/size`，提交时不再注入提示词构造层。
- **BFF `GenerationService.acceptNode`**：复用与 `accept()` 完全一致的
  `解析模型 + 访问控制 + 服务端权威算价 + 预扣 + 交编排器` 全链路，仅 `platform_config_id` 显式传 `null`。
  计费/扣费安全红线（价格服务端算、预扣失败即退款）保持不变。
- **编排器 `llm_router._with_constructed_prompt`**：对 `image/video` 当 `platform_config_id` 为空时
  `if not pc_id: return req`，原样使用节点 prompt——行为正确且零成本。
- **电商套图** 继续走 `POST /generation/jobs`（保留 `platformConfigId` 能力），互不影响。

前端 `NodeChatPrompt.submit()` 的图片/视频分支改为调用 `acceptNodeGenerationJob()`
（→ `/generation/node`）；`catalog.ts` 新增 `AcceptNodeJobInput` + `acceptNodeGenerationJob`。

## Consequences
- **易**：节点与电商套图的参数拼装可独立演进，互不复用 DTO；新增节点专属校验/字段不影响电商。
- **易**：节点生成不再依赖 `platform_configs` 表存在，降低节点功能的耦合面。
- **难（代价）**：多一条端点 + 一个 service 方法需维护；两类受理逻辑目前是"复制式"共享，
  若计费红线逻辑未来变更需同步两处（可接受：当前两处均薄，且差异点 `platform_config_id` 是唯一分叉）。
- **验证**：E2E 网络拦截确认节点提交命中 `/generation/node` 且未命中 `/generation/jobs`，响应 201。
