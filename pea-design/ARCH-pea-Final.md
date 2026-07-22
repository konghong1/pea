# pea Creative OS — 终版开发架构（锁定版）

> **状态：开发基线（LOCKED）**。本文档是 pea Creative OS 的**架构设计终稿**，整合 `PRD-pea-Creative-OS.md`、`ROADMAP-pea-Creative-OS.md`、`DESIGN-Core-Subsystems-100k.md`、`TECH-SELECTION-pea.md` 并锁定决策：**① 主库用 MySQL；② 生成=调用外部大模型**。后续开发以本文为准（早期"建议 PostgreSQL"的架构草案已作废并移除）。
> 容量基线：约 **10 万用户 / DAU 2 万 / 日生成 ~6k**。

---

## 1. 已锁定决策总表（开发就照这个来）

| # | 决策 | 锁定值 |
|---|---|---|
| D1 | 架构形态 | 模块化单体起步（单仓/单部署），按负载与团队边界逐步抽服务 |
| D2 | 前端 | React 18 + TS + React Flow + Zustand + Tailwind + antd v5 + Vite |
| D3 | BFF / API 网关 | Node.js + NestJS（REST + WebSocket/SSE） |
| D4 | 生成编排 | Python + FastAPI（Worker） |
| D5 | 生成方式 | **调用外部大模型**（图/视频/LLM），经 LiteLLM 统一路由 + 回退 |
| D6 | 主数据库 | **MySQL 8**（JSON 列存画布/规划，生成列建索引） |
| D7 | 缓存 / 队列 | Redis（余额缓存 + 生成任务队列 Redis Streams） |
| D8 | 媒体存储 | S3 兼容对象存储 + CDN（预签名直传） |
| D9 | 向量检索 | **后期**单独引入 Qdrant（不在 Now 阶段） |
| D10 | 编排引擎 | Now：Celery/Redis Streams 跑通；Next：迁 Temporal |
| D11 | 基建 | Docker + K8s（GPU worker 独立池）+ OTel + Prometheus + Grafana |
| D12 | 一致性边界 | 仅"积分预扣/退还"走强一致事务；其余事件 + 补偿最终一致 |

---

## 2. 系统上下文与限界上下文（不变）

```
用户(创作者) ──► pea Creative OS ──► 外部大模型供应商(图像/视频/LLM)
                    │
                    ├── 对象存储/CDN（媒体）
                    └── 支付/计费（积分 Tapies，内部）
```

限界上下文（模块边界，抽服务时据此切）：
- **Identity & Account**（鉴权/账户/积分钱包）
- **Canvas & Workflow**（画布编辑器/节点/自动保存）
- **Generation Orchestration**（生成受理/编排/Worker/回退）★重心
- **E-commerce Suite**（电商套图）
- **Community / TapTV**（社区/作品/feed）
- **Notification**（WS/SSE 推送）

---

## 3. 容器架构图（C4 Level 2）

> 见文末可视化图 `system_container_view`。文字版如下：

| 容器 | 技术 | 职责 |
|---|---|---|
| Web SPA | React + Vite | 画布/电商/社区/账户全部前端交互 |
| CDN | 云 CDN | 前端静态资源 + 媒体分发 |
| BFF / API 网关 | Node NestJS | 鉴权、限流、聚合、WS 推送、文件预签名 |
| Generation Orchestrator | Python FastAPI | 受理生成、入队、Worker、状态机、补偿退还 |
| AI 路由层 | LiteLLM | 统一接入外部大模型、限流、成本、自动回退 |
| 外部大模型 | MJ/Kling/OpenAI/… | 真实出图/出视频/文案（D5） |
| MySQL | MySQL 8 | 主库：用户/画布/规划/积分账本/任务/作品 |
| Redis | Redis | 余额缓存 + 生成队列 + 限流计数 |
| 对象存储 | S3 兼容 | 用户上传图、生成产出媒体 |
| 可观测 | OTel+Prom+Grafana | 全链路 trace / 指标 / 看板 |

**关键调用链**：SPA → BFF（校验+预扣积分+返 jobId，<2s）→ Redis 队列 → Worker（FastAPI）→ LiteLLM → 外部大模型 → 回调更新 job → BFF 经 WS 推送进度/结果。

---

## 4. 数据层：MySQL 落地要点（D6）

### 4.1 灵活结构存储策略
- **画布图、生成规划**等变结构数据 → `JSON` 列（如 `canvases.graph_json`、`generation_plans.steps_json`）。
- 需查询/过滤的字段 → **生成列（Generated Column）+ 索引**，例如：
  ```sql
  ALTER TABLE canvases
    ADD COLUMN node_count INT AS (JSON_LENGTH(graph_json->'$.nodes')) STORED,
    ADD INDEX idx_node_count (node_count);
  -- 多值索引（标签等数组）
  ALTER TABLE generation_plans
    ADD INDEX idx_tags ((CAST(steps_json->'$.tags' AS UNSIGNED ARRAY)));
  ```
- 强结构数据（用户、积分账本、任务、作品）→ 普通表 + 关系约束。

### 4.2 核心表（Now 阶段最小集）
| 表 | 关键字段 | 说明 |
|---|---|---|
| users | id, email, password_hash, created_at | 账户 |
| accounts | user_id, balance, version | 积分钱包，**version 乐观锁** |
| ledger_entries | id, user_id, txn_id(唯一), type, debit, credit, created_at | **双记账本**，按月分区 |
| canvases | id, owner_id, title, graph_json, version, updated_at | 画布，JSON 存节点/连线 |
| canvas_versions | id, canvas_id, version, graph_json, created_at | 版本历史 |
| generation_jobs | id(jobId), user_id, status, payload_json, result_json, created_at | 生成任务状态机 |
| generation_plans | id, job_id, steps_json, status | 电商出图规划 |
| products / product_images | id, user_id, plan_id, image_url, attrs_json | 电商套图产出 |
| works / community_posts | id, user_id, media_urls, caption, created_at | 社区作品 |

> 完整 DDL 可另出一份 `SCHEMA-pea-MySQL.sql` 直接建表（需要我补）。

---

## 5. 生成管道（调用外部大模型，D5）

**状态机**：`queued → running → done / failed → refunded(失败补偿)`。
**幂等**：`idempotency_key` 防重复扣费/重复生成。
**回退**：Provider A 失败/限流 → LiteLLM 自动切 B（如图像主用 MJ，回退 SD/OpenAI；视频主用 Kling，回退备选）。
**补偿**：Worker 终态 failed → 触发积分退还（走 ledger 反向借贷两行）。
**限流/断路器**：每用户并发上限 + Provider 预算 + 断路（成本失控为头号风险）。

---

## 6. 代码仓库布局（重要：与产品设计目录分离）

> **目录约定**：`pea-design/` 是**产品设计路径**（HTML 原型 + 全部文档 PRD/ARCH/ROADMAP/DESIGN/TECH）。**代码仓库放在 `pea-design/` 的同级目录**，不要嵌套进 `pea-design/` 内（避免原型/文档与代码混在一起、仓库职责不清）。

建议代码仓库命名 `pea-server/`（**命名可改**，见下方说明），结构如下：

```
pea-server/                # 与 pea-design/ 同级（实际开发仓库）
├── web/                      # React SPA (D2)
├── services/
│   ├── bff/                  # Node NestJS (D3): modules/identity, canvas, generation, community, billing
│   ├── generation-orchestrator/  # Python FastAPI (D4): api, worker, llm_router(LiteLLM), compensations
│   └── shared/               # 公共类型/事件契约
├── infra/
│   ├── docker/               # Dockerfile (bff, orchestrator, worker)
│   ├── k8s/                  # deployment + gpu-worker-pool
│   └── mysql/init/           # 初始化 SQL
└── README.md                 # 指向 ../pea 的设计文档（PRD/ARCH/...）
```

**两个目录的同级关系**（在 `D:\workspace\pea\` 下）：

```
D:\workspace\pea\
├── pea-design/           # 产品设计路径：原型 HTML + 文档
└── pea-server/    # 代码仓库：web/ services/ infra/（实际开发）
```

> 代码仓库命名说明：`pea-server` 仅为建议占位。若你们已有固定仓库名（如 `creative-os`、`pea-platform`），直接替换顶层目录名即可——内部 `web/ services/ infra/` 结构不变。文档其余章节引用"代码仓库"时，均指这个 `pea-design/` 的同级目录。

模块依赖方向：bff → generation-orchestrator（仅受理/查询 API），orchestrator 内部 worker 调 LiteLLM；db/repo 层封装在各自模块内，禁止跨模块直连表。

---

## 7. ADR 更新

| ADR | 标题 | 状态 |
|---|---|---|
| ADR-001 | 演进式模块化单体 | Accepted |
| ADR-002 | 生成异步解耦 | Accepted |
| ADR-003 | 画布用 React Flow | Accepted |
| ADR-004 | AI 路由用 LiteLLM | Accepted |
| ADR-005 | 主库用 **MySQL 8**（JSON 列 + 生成列索引） | **Accepted（本次新增）** |
| ADR-006 | 积分双记账本 | Accepted |
| ADR-007 | WS/SSE 实时推送 | Accepted |
| ADR-008 | 主库用 PostgreSQL | **Deprecated（被 ADR-005 取代）** |
| ADR-009 | 生成=调用外部大模型（LiteLLM 路由+回退） | **Accepted（本次新增）** |

---

## 8. 开发起步清单（按此顺序 scaffold）

1. **基础设施**：MySQL 实例 + Redis + S3 bucket + CDN；docker-compose 本地一把起。
2. **BFF 骨架**：NestJS 模块划分 + JWT 鉴权 + 限流中间件 + 文件预签名接口。
3. **账户 + 积分**：users/accounts/ledger 表 + 预扣/确认/退还事务（双记账本先通）。
4. **画布自动保存**：canvases/canvas_versions + debounce 保存 + version 乐观锁（补掉"刷新即丢"痛点）。
5. **生成受理**：generation_jobs 表 + BFF 受理接口（校验+预扣+返 jobId）。
6. **Worker + LiteLLM**：FastAPI worker 消费队列 → 调外部模型 → 回写状态 → WS 推送；失败补偿退积分。
7. **电商套图**：products/product_images + 出图规划前端串联。
8. **社区/账户页**：在核心跑通后补。

> 重心永远是 **生成管道（D5/D9）+ 积分账本（D6）** 两条线先打通，再扩功能。

---

## 9. 仍须管理的风险（开发期持续看）

- **R1 成本失控**：Provider 预算 + 断路器 + 每用户配额，尽早做。
- **R2 外部模型不稳定**：回退链路 + 重试 + 超时，必须覆盖。
- **R3 媒体存储成本**：S3 生命周期（标准→IA→归档）从第一天配。
- **R4 积分错账**：每日对账脚本 + 双记账本，作为最后兜底。
- **R5 MySQL JSON 查询性能**：监控大画布 JSON 读写，必要时拆热点字段到生成列。
