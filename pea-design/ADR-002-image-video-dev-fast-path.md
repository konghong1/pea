# ADR-002: 图像/视频生成开发期极速开关 (Mock 兜底)

## Status
Superseded by ADR-003（默认开启的 Mock 路径已移除；`PEA_FORCE_MOCK_TYPES` 开关代码保留，仅作可选联调工具，默认不再开启）

## Context
用户反馈「点击生成图片时生成很慢」，期望 1~3 秒出图。排查结论：

- 生成链路本身无瓶颈：BFF 受理 → Redis 入队 → Worker 消费，均为毫秒级。
- 真正的耗时在**模型调用**。默认图像模型 `agnes-image-2.0/2.1-flash` 走真实 Agnes
  提供商（`openai-compatible`，`https://apihub.agnes-ai.com/v1`）。`worker.py` 注释明确：
  **Agnes 单张出图 18~77s 且波动大**。这是物理上限，无法靠架构优化压到 1~3s。
- 仓库已有 `MockProvider`：本地生成占位 SVG，`time.sleep(0.3)` 后返回，约 0.3s 出图。
  但 `route()` 按 `model_id` 从 DB 解析提供商，种子模型全是 `openai-compatible`（真实），
  不存在 mock 模型；且 `PEA_ALLOW_MOCK_FALLBACK=false`（生产不允许失败静默回退假图）。

结论：在**开发/联调/演示**环境，1~3s 只能通过 Mock 路径达成；生产仍走真实提供商。

## Decision
新增可反转的环境开关 `PEA_FORCE_MOCK_TYPES`（逗号分隔的 `type` 列表）：

- `app/config.py`：`force_mock_types: str = ""`，并提供 `@property force_mock_types_set`
  （避免 pydantic-settings 对 `list[str]` 的 JSON 解析失败——这是初版用 `list[str]` 字段导致
  服务启动崩溃的根因，已改为 `str` + 属性）。
- `app/llm_router.py` `route()`：在解析 DB 模型**之前**，若 `req['type'] in force_mock_types_set`
  则直接 `return _mock.generate(req)`，跳过 DB 解析与真实模型调用。
- `docker-compose.yml`（generation-orchestrator）：`PEA_FORCE_MOCK_TYPES: "image,video"`
  对本开发环境默认开启。
- `app/worker.py`：XREADGROUP `block` 1000→200ms（加快任务拾取）；在 `route()` 前后加
  `route() for job {id} took {dt:.2f}s` 日志，便于后续排查耗时。

## Consequences
- 易（开发环境）：图像/视频生成 ~0.5s 出图（实测端到端 0.49s，模型调用 0.30s），满足 1~3s。
- 易（可逆）：删掉 docker-compose 里那一行即恢复真实提供商，无需改代码。
- 代价：开发期图像是占位 SVG（渐变 + 提示词文字），非真实成图。真实效果需关掉开关走 Agnes。
- 代价：视频同样走 mock（同步返回占位 mp4 URL），不走真实异步轮询。
- 生产护栏不变：`allow_mock_fallback=false` 仍生效，真实提供商失败 → FAILED + 退款，不回退假图。
- 文本节点未纳入此开关（用户只提图片）；文本仍走真实 Agnes SSE。如需整体联调提速，
  可把 `text` 也加入 `PEA_FORCE_MOCK_TYPES`。

## 验证
- `verify/verify_e16_text_content_and_image_speed.py`：图片生成 0.49s 出图、0 console error；
  文本节点生成内容落入内容区（旧 `.pea-node-chat-body` 块已删除）。
- 编排器日志：`type 'image' in force_mock_types -> MockProvider` + `route() ... took 0.30s (provider=mock)`。
