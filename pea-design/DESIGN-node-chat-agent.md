# 节点聊天 Agent 架构设计草案 v0.1（待确认）

> 目标：在画布"节点输入框"输入聊天信息 → 按节点类型调用不同模型 → 结果渲染回节点；
> 同时设计 Tapies 扣费 / 失败回退 / token 用量统计的可扩展方案。
> 本稿只做设计与流程图，**不写业务代码**，确认后再进入开发。

---

## 0. 需求清单（来自你的原话）

1. 在节点的输入框输入聊天信息后，调用对应的聊天接口。
2. **不同节点调用不同模型**，返回结果也不同（文本 / 图片 / 视频）。
3. 输出内容**放在节点中**渲染。
4. **文本节点内容超长 → 文本节点出现滚动条**（固定高度，不自动撑开）。
5. **视频 / 图片节点**生成的内容**把节点撑开**（媒体决定尺寸）。
6. 设计 Agent，画出流程图：**怎么扣 Tapies、失败怎么回扣**。
7. 预留 **token 用量统计** 扩展点，验证"像 learn-claude-code 那样是否好扩展"。
8. **图片/视频生成需独立的提示词构造层**：基于用户聊天 + 用户选择的**平台配置**构造平台化提示词；
   不同平台（DALL·E / SD / MJ / Runway / Pika…）提示词格式不同，需独立成层、可插拔。

---

## 1. 从 learn-claude-code 学到的设计思想（可复用部分）

该仓库是一个"类 Claude Code 的极简 harness"教学工程，核心哲学是 **Agent = 模型 + Harness（外壳）**。
通读 `s01`~`s20` 后，有 4 条模式可直接映射到我们的节点聊天 Agent：

| 仓库模式 | 代码位置 | 映射到我们的系统 |
|---|---|---|
| **核心循环不变** `while stop_reason==tool_use` | `s01_agent_loop/code.py` | 我们的"节点对话"也是一轮请求→模型→结果回填→（多轮）循环，主循环结构保持稳定 |
| **分发映射表** `TOOL_HANDLERS = {name: fn}` | `s02_tool_use/code.py` / `s20 BUILTIN_HANDLERS` | 用 `NodeModelRegistry`：节点类型 → 模型适配器（text/image/video）。**新增模型=加一行注册，零侵入** |
| **错误恢复** `RecoveryState` + `with_retry`（指数退避、429/529 退避 + fallback model、prompt_too_long 压缩） | `s11_error_recovery/code.py` | 用 `RecoveryPolicy`：模型失败/超时/限流时退避重试、必要时回退备用模型；**失败路径触发回扣** |
| **钩子缝** `HOOKS["PreToolUse"/"PostToolUse"]` 横切关注点 | `s20` `HOOKS` + `register_hook` | 用 `PostGenerationHook`：计费确认 + **token 用量记录 + 审计**，从主循环剥离 |

**重要诚实结论**：grep 全仓库 `usage|cost|billing|token|metering` → **0 命中**。
该仓库**完全没有 token 计量/计费逻辑**。所以它的"好扩展"指的是它那套
**注册表 + 钩子分层**的工程结构适合承载扩展；计量层本身要我们参照同样哲学自己建
（第 6 节给出具体做法，正好复用它的钩子缝）。

---

## 2. 整体架构（复用现有 pea-server，不重复造轮子）

完全建立在已落地的"薄 BFF + 厚编排器 + 双记账本"之上：

- **复用**：`BFF GenerationService`(受理/算价/预扣) → `Orchestrator`(落库/队列/调模型) → `BillingService.preauthorize/refund` + `accounts/ledger_entries` → `Redis events` → `BFF WS` → 前端回填。
- **复用**：`PricingService.computeCost`（服务端权威算价，纯函数）、`NodeChatPrompt.tsx`（选中节点→输入→提交→WS 回填交互）。
- **新增/扩展**：
  - BFF 新增 **`agent` 受理模块**（或并入 `generation`）：处理"节点聊天"请求，预扣按节点所选模型定价。
  - Orchestrator 新增 **`NodeModelRegistry` + `GenerationDispatcher`**：按 `node.kind` 选择适配器与模型。
  - Orchestrator 新增 **`PromptConstructionLayer` + `PromptComposerRegistry`**：图片/视频生成前，按用户所选
    **平台配置**把聊天内容构造为平台化提示词（`plain` 模板 / `llm` 扩写两种模式），是防腐层（ACL）。
  - 适配器层解析模型返回的 **`usage`**（prompt/completion tokens）并透传。
  - 新增 **`PostGenerationHook`**：写 `usage_records`、触发计费确认。
  - BFF 新增 **SSE `chat.message` 端点**（节点聊天流式专用，轻量）；WS `job.updated` 仅保留给慢/长时生成任务。
    聊天流经 `txn_id` 与 `BillingService` 桥接（预扣/回扣通知复用现有双记账本）。
  - 前端：`PeaNode` 按 kind 渲染（文本滚动条 / 媒体撑开）。

---

## 3. 关键抽象（对齐仓库哲学）

```
NodeModelRegistry   # 类比 TOOL_HANDLERS
  text   -> TextLLMAdapter       (对话/续写/摘要...)
  image  -> ImageGenAdapter      (文生图)
  video  -> VideoGenAdapter      (文生视频)

GenerationDispatcher
  dispatch(node) -> 选适配器 + 选模型(model_id 来自节点/用户选择)
                  -> adapter.call(prompt, params, recovery_policy)

RecoveryPolicy     # 类比 RecoveryState + with_retry
  max_retries / backoff(指数+jitter) / fallback_model / 触发 refund_on_failure

PostGenerationHook # 类比 HOOKS
  on_success(result): record_usage + billing.confirm/settle
  (计量/审计/计费确认 全部挂这里，核心循环不感知)
```

**为什么这样对应**：仓库证明——"能力 = 注册表条目，横切 = 钩子"是低成本扩展的结构。
我们要加一种新节点模型，只需在 `NodeModelRegistry` 加一行；要加一类统计，只需挂一个钩子。
核心 `dispatch → call → render` 循环永远不动。

---

## 3.5 提示词构造层（图片 / 视频生成专属）★新增

你提出的需求：图片/视频生成时，要**基于用户聊天内容 + 用户选择的平台配置**来构造提示词。
这不是"把聊天原文直接丢给模型"，而是一个独立的**提示词构造层（Prompt Construction Layer）**——
它位于「节点聊天意图」与「平台适配器」之间，是用户自由输入与平台提示词格式之间的**防腐层（ACL）**。

### 为什么必须独立成层
- **平台提示词格式各不相同**：DALL·E / Stable Diffusion / Midjourney / Runway / Pika 各自有
  不同的 prompt 约定（风格前缀、负向词、宽高比、画质标记）。把"聊天→平台 prompt"的映射
  硬编码进 `ImageGenAdapter`/`VideoGenAdapter` 会让适配器膨胀，且每加一个平台都要改适配器。
- **平台配置是用户态数据**：provider、模型、风格预设、负向词、宽高比、画质、是否用 LLM 扩写，
  都来自用户"AI Provider 设置"里选的**平台配置**（一个聚合，按节点或按用户引用）。
- **可插拔 = 加平台只加一个 composer**：用 `PromptComposerRegistry` 对齐仓库的注册表哲学，
  新增平台只需注册一个 `compose()`，`dispatch` 核心循环不动。

### 关键抽象
```
PlatformConfig          # 来自"AI Provider 设置"的聚合（按 id 引用）
  provider / model
  presets: { style, aspect_ratio, negative_prompt, quality, lang, ... }
  prompt_mode: 'plain' | 'llm'     # 直接模板 vs 先 LLM 扩写再拼预设

PromptComposerRegistry  # 类比 TOOL_HANDLERS / NodeModelRegistry
  'dalle'     -> DalleComposer(plain)
  'sdxl'      -> SdxlComposer(plain + negative_prompt)
  'midjourney'-> MjComposer(plain + --ar/--style 参数)
  'runway'    -> RunwayComposer(llm 扩写 + 时长/比例)
  'pika'      -> PikaComposer(llm 扩写 + 运动强度)
  'default'   -> DefaultComposer(llm 兜底)

PromptConstructionLayer
  compose(chat, platformConfig) -> GenerationPrompt
    ├─ prompt_mode=='plain': 模板注入（chat + presets 拼装），无额外 LLM 调用
    └─ prompt_mode=='llm'  : 先调 TextLLM 把 chat 扩写成平台化描述（消耗 token，记 usage）
                              -> 再拼 presets
  return GenerationPrompt{ prompt, params:{aspect_ratio, negative_prompt, quality, ...} }

GenerationDispatcher(媒体节点)
  dispatch(node):
    cfg = PlatformConfigRepo.get(node.platform_config_id)   # 用户选择的平台配置
    gp  = PromptConstructionLayer.compose(chat, cfg)         # ★新层：聊天+配置 -> 平台化提示词
    adapter = NodeModelRegistry.get(node.kind)              # image/video 适配器
    adapter.call(gp, recovery_policy)
```

### 关键决策（已确认 / 待确认）
- **prompt_mode（已确认）**：两种模式都保留，由每个 `PlatformConfig` 自带的 `prompt_mode`
  （`plain` / `llm`）决定；plain 零额外成本，llm 先调 TextLLM 扩写再拼预设。
- **平台配置引用粒度（已确认）**：**节点级** `platform_config_id`——每个节点在配置时选择自己的平台配置；
  未绑定时回退"用户默认平台配置"兜底。来源复用现有"AI Provider 设置"聚合。
- **LLM 扩写的 token**：`prompt_mode=='llm'` 那次扩写本身是一次 LLM 调用，其 `usage`
  同样由 `PostGenerationHook` 记录（见第 6 节），保证 token 统计完整。
- **构造层位置（待确认）**：见下方"BFF vs Orchestrator"说明，需你拍板放哪一层。


---

## 4. Tapies 扣费与失败回退流程（重点）

沿用现有**双记账本**红线：价格服务端算、客户端不传金额；余额变更必须事务+行锁+锁内幂等；失败必须退款而非静默假结果。

### 4.1 状态机

```
接请求 ──preauthorize(txn_id, estCost)──▶ 预扣成功
   │                                        │
   │ 余额不足                                ▼
   └──▶ 422 提示用户                 调模型(adapter.call)
                                           │
                              ┌────────────┴────────────┐
                          成功                         失败/超时/限流
                          │                             │
                          ▼                             ▼
                 流式回填节点                RecoveryPolicy 退避重试
                 渲染文本(滚动)/媒体(撑开)        │ 重试耗尽?
                          │                     ├─否─▶ fallback model 重试(不重复扣)
                          ▼                     └─是─▶ refund_on_failure()
                 PostGenerationHook                       │
                  record_usage + confirm/settle           ▼
                          │                       job=FAILED→REFUNDED
                          ▼                       WS 通知前端"失败已回扣"
                 结束(余额已结算)
```

### 4.2 关键规则

- **预扣时机**：每次"节点对话轮"受理时 `preauthorize`，`txn_id` 由 BFF 生成并锁内幂等（防双扣）。
- **重试不重复扣**：`RecoveryPolicy` 的重试 / fallback model 切换**复用同一 txn_id**，不新建预扣；只有真正新的一轮对话才新预扣。
- **失败回退**：Orchestrator `compensation.refund_on_failure()` 经 `/internal/billing/refund`（service token 鉴权，3 次指数退避）→ `BillingService.refund` 行锁 + 锁内幂等 → 回加余额，流水 `type='refund'`。
- **对账兜底**：`scripts/reconcile_ledger.py` 每日扫描 `generation_jobs` 终态与 `ledger_entries` 不一致项，自动补偿。
- **预估展示**：前端 `NodeChatPrompt` 已调用 `estimateCost()` 实时显示本轮预估 Tapies，保持。

### 4.3 ADR 草拟

```
# ADR-NCA-01: 节点聊天按轮预扣、失败退款
Status: Proposed
Context: 节点对话是 LLM 调用，成本不可忽略，需防超支与误扣。
Decision: 复用现有 preauthorize/refund 双记账本；每轮对话预扣，失败/超时触发 refund_on_failure；重试与 fallback 模型不重复扣费。
Consequences: 一致性强、无双扣双退；代价是每次对话多一次事务写（可接受，DAU 2万量级）。
```

---

## 5. 前端渲染规范（文本滚动 vs 媒体撑开）

基于现有 `PeaNode.tsx` + `NodeChatPrompt.tsx`：

| 节点类型 | 渲染行为 | 实现要点 |
|---|---|---|
| **文本节点** | 内容超长 → **固定 max-height + `overflow-y:auto` 滚动条** | 与现有 contentEditable 不同：聊天回复放进独立 `.pea-node-chat-body` 容器，设 `max-height`（如 320px），超长出现滚动条，**不撑高节点** |
| **图片节点** | 生成结果 `resultUrl` → `<img>`，**节点按媒体尺寸撑开** | 复用 `isMedia` 分支；generating 显示 spinner；完成后容器 `height:auto` 包住图片 |
| **视频节点** | 生成结果 `resultUrl` → `<video controls>`，**撑开节点** | 同上；视频自带控件，节点高度随视频比例 |

要点：**文本"限高滚动"与媒体"撑开"是两个互斥的布局策略**，由 `node.kind` + 是否有 `resultUrl` 决定，不混用。

---

## 6. Token 用量统计的扩展性（重点回答）

### 6.1 现状
现有 pea-server **无任何 token 计量**：计费走 `ai_models.pricing_json` 的**参数化 Tapies 定价**
（尺寸/时长/数量），`agnes_provider._generate_text` 连 `usage` 都没解析，`ledger_entries` 只记金额不记 token。

### 6.2 扩展方案（套用仓库"注册表 + 钩子"哲学，核心循环不动）

1. **适配器透传 usage**：在 `agnes_provider._generate_text` 等适配器解析 `response.usage`
   （`prompt_tokens` / `completion_tokens`），写入 `GenerationResult.usage`；`router` 不感知。
2. **挂钩子记录**：新增 `PostGenerationHook('usage')` → 写 `usage_records` 表
   （维度：user / node_id / job_id / model / prompt_tokens / completion_tokens / 时间戳）。
   这一步**不改 dispatch 循环**，正是仓库 `HOOKS` 缝的价值。
3. **可选：按 token 计费**：`PricingRule` 增加 `per1kTokens` 档 → `PricingService.computeCost` 支持 token 维度
   （纯函数扩展）；`ledger_entries.type` 增加 `chat`/`token` 类别。

### 6.3 结论
**像 learn-claude-code 这样（注册表 + 钩子分层）是好扩展的**——因为它把"能力"和"横切关注点"
都做成了可插拔的 seams。仓库本身没做计量，但我们要补的计量层，**恰好能挂在它示范的钩子缝上**，
无需改动主循环。这正是该设计"可演进、不重写"的体现。

---

## 7. 待你确认的关键决策（拍板后进入开发）

1. **扣费粒度**：每轮对话预扣（推荐，已设计） vs 会话级预扣？
2. **失败重试的计费语义**：重试/fallback 不重复扣（推荐）是否认可？
3. **token 统计范围**：先做"展示/审计"（写 `usage_records`）还是直接"按 token 计费"？
4. **流式输出通道**：~已确认~ 新增 SSE `chat.message`（聊天轻量专用，与生成任务流分离）；WS `job.updated` 仅用于慢/长时生成任务。
5. **节点类型范围**：本期支持 text/image/video 三种（你提到的），还是把 story/world3d 等也纳入？
6. **提示词构造模式**：~已确认~ 两种模式都保留，由 `PlatformConfig.prompt_mode` 决定（plain / llm）。
7. **平台配置来源/粒度**：~已确认~ 复用"AI Provider 设置"作 `PlatformConfig` 聚合；**节点级** `platform_config_id`，未绑回退用户默认。
8. **构造层位置**：~已确认~ 放 Orchestrator（复用模型路由/计费，llm 扩写顺手做、token 易记）。

---

## 附：复用清单（避免重复造轮子）

- `services/bff/src/modules/billing/billing.service.ts` — `preauthorize/refund`
- `services/bff/src/modules/generation/generation.service.ts` — `accept()` 受理范式
- `services/bff/src/modules/providers/pricing.service.ts` — `computeCost` 纯函数
- `services/generation-orchestrator/app/compensation.py` — `refund_on_failure`
- `web/src/components/NodeChatPrompt.tsx` — 输入/算价/提交/回填交互
- `web/src/components/PeaNode.tsx` — 节点渲染（文本滚动 / 媒体撑开改造点）
- `web/src/store/canvas.ts` — `registerJob/applyJobResult` 回填通道
