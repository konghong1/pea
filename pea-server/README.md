# pea-server — pea Creative OS 代码仓库

> 本仓库是 **pea Creative OS** 的实际开发代码（与产品设计文档 `../pea-design/` 同级，互不嵌套）。
> 设计基线请读 `../pea-design/`：`ARCH-pea-Final.md`(架构) / `PRD-pea-Creative-OS.md`(需求) / `TASK-BREAKDOWN-pea.md`(任务) / `ROADMAP-pea-Creative-OS.md`(里程碑)。
>
> 品牌统一为 **pea**（原 tapnow 已全量重命名为 pea，见 `../pea-design/`）。

---

## 1. 架构总览（对齐 ARCH-pea-Final.md）

```
Web(SPA) ──► BFF(NestJS) ──► Generation Orchestrator(FastAPI) ──► 外部大模型(LiteLLM)
                │                    │
            MySQL 8 / Redis      Redis Streams(队列) + 事件频道
            MinIO(S3 兼容)        Worker 消费 → 回写 → WS 推送
```

- **重心两条线已打通（脚手架可运行）**：生成异步管道 + 积分双记账本。
- 模块边界（ARCH §6）：BFF **不直连** `generation_jobs` 表，只通过 HTTP 调编排器；编排器失败退款时调 BFF `/internal/billing/refund`，不直连 `accounts/ledger`。

### 目录结构

```
pea-server/
├── docker-compose.yml          # 一键起 MySQL+Redis+MinIO+BFF+Orchestrator+Web
├── infra/
│   ├── mysql/init/01-schema.sql # MySQL 8 DDL(JSON列/生成列索引/ledger按月分区/乐观锁)
│   └── docker/                  # 三个 Dockerfile + nginx 反代 + .dockerignore
├── services/
│   ├── shared/                  # 跨服务事件契约(与 Python 镜像一致)
│   ├── bff/                     # NestJS: auth/billing/generation/files/canvases/gateway
│   └── generation-orchestrator/ # FastAPI: 状态机/队列/Worker/LiteLLM路由/补偿
└── web/                         # React18+TS+Vite+ReactFlow+Zustand+antd v5
```

---

## 2. 快速开始（Docker，推荐）

```bash
cd pea-server
docker compose up --build
# 等待 healthy: mysql / redis / minio 就绪后 BFF 与 Orchestrator 自动启动
```

- Web:        http://localhost:8080
- BFF:        http://localhost:4000
- Orchestrator: http://localhost:8000/api/health

首次启动 `infra/mysql/init/01-schema.sql` 会自动建表（幂等）。任意邮箱注册即赠送 1000 Tapies。

### 本地分服务开发（无 Docker 时）

```bash
# 1) 起依赖: MySQL8 / Redis7 / MinIO(可用本仓库 docker-compose 仅起这三项)
docker compose up -d mysql redis minio

# 2) BFF
cd services/bff && cp .env.example .env && npm i && npm run start:dev

# 3) Orchestrator
cd services/generation-orchestrator && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000

# 4) Web
cd web && npm i && npm run dev   # http://localhost:5173 (vite 已代理 /api 与 /ws 到 :4000)
```

---

## 3. 核心 API 契约

| 方法 | 路径 | 说明 | 模块/任务 |
|---|---|---|---|
| POST | `/auth/register` `/auth/login` | 注册/登录返回 JWT | auth / T-ACC-01 |
| GET  | `/users/me` | 当前用户 | users |
| GET  | `/billing/balance` | 余额（顶栏展示） | billing / T-ACC-02 |
| GET  | `/billing/ledger?page=&size=` | 积分流水 | billing / T-ACC-05 |
| POST | `/generation/jobs` | 受理生成（预扣→返 jobId, p95<2s） | generation / T-GEN-02 |
| GET  | `/generation/jobs/:id` | 任务状态/结果 | generation / T-GEN-01/08 |
| GET  | `/generation/jobs?limit=&cursor=` | 历史 | generation |
| POST | `/files/presign` | S3 预签名直传 | files / T-FILE-01 |
| GET  | `/files/url?key=` | 强制签名访问 | files / T-FILE-03 |
| POST | `/canvases` | 建画布 | canvases / T-CANVAS-SAVE |
| PUT  | `/canvases/:id` | 自动保存（乐观锁, 冲突 409） | canvases / T-CANVAS-SAVE-02/03 |
| GET  | `/canvases/:id` | 取画布 | canvases |
| POST | `/internal/billing/refund` | **内部**失败补偿退款（service token） | billing / T-GEN-07 |
| WS   | `/ws` | 鉴权后接收 `job.updated`/`balance.changed`/`notification` | gateway / ADR-007 |

生成受理状态机：`queued → running → done / failed → refunded`（非法跳转被拒，见 `app/models.py`）。

---

## 4. 代码质量与团队规范（资深开发把关要点）

1. **强一致记账**：`accounts.version` 乐观锁 + 事务 + `ledger_entries.txn_id` 唯一幂等，重复预扣/退还不双扣（ARCH R4）。
2. **生成不出图**：编排器只调外部模型，成功/失败均回写并发布事件；失败经 BFF 退款。
3. **护栏优先**：限流中间件（生产换 Redis）、每用户并发软上限、Provider 主备回退（ARCH R1/R2）。
4. **契约单一源**：跨服务事件在 `services/shared/` 同时维护 TS 与 Python 两份，**改一侧必同步另一侧**。
5. **前端自动保存**：debounce 1s + 失焦/关闭前保护 + 乐观锁 409 冲突提示，根治"刷新即丢"。
6. **主题**：Web 内置 浅/深/跟随 三态切换（antd `darkAlgorithm` + Tailwind `dark` class）。

---

## 5. 实现进度（2026-07-22 首版脚手架）

| Epic | 范围 | 本仓库状态 |
|---|---|---|
| E0 基础工程 | 仓库/compose/DDL/CI | ✅ 仓库+compose+DDL 完成；CI(⏳ 待补) |
| E1 账户与积分 | 注册/余额/双记账本/对账 | ✅ 注册登录/余额/双记账本/流水 已实现；每日对账脚本(⏳) |
| E2 生成管道 ★ | 受理/队列/Worker/LiteLLM/补偿/历史 | ✅ 全链路打通（mock provider 本地可跑，LiteLLM 接入口预留） |
| E3 画布自动保存 | 表/debounce/乐观锁 | ✅ 实现 |
| E4 文件存储 | 预签名/Worker写/签名访问 | ✅ 预签名+签名访问；Worker 写产出(⏳ 接真实模型后启用) |
| E5 画布编辑器 M1 | 节点/连线/Inspector/Agent/生成 | ✅ ReactFlow+自动保存+生成接入 + Agent对话面板(规则引擎) + 富文本工具条 + 侧边面板(搜索/评论/历史/文件) + 右键菜单+快捷键 |
| E6 电商套图 M2 | — | ⏸ 搁置（决策不变） |
| E7 全局系统 G | 顶栏积分/Toast/通知/分享/AI Provider | ✅ 顶部导航SPA切换 + 全局Toast + 分享复制 + 通知中心(WS) + 用户菜单(统计/退出) + AI Provider配置(列表/开关/默认回退/持久化) |
| E8 主页+账户 | Workspace/账户中心/AI Provider管理 | ✅ 主页(欢迎/快捷/最近项目/新建) + 账户中心(资料/余额/积分流水) + AI Provider设置页(T-M5-02复用) |
| E9 社区 TapTV | feed/发布 + 作品详情/点赞/收藏/评论 + 竞技场 Non-Goal 占位 | ✅ 社区后端(community 模块 + works 互动三表) + TapTV 真实卡片流/发布弹窗/详情抽屉/点赞收藏评论切换 + 竞技场明确移出 MVP |
| E10 质量门 | 单测/E2E/性能/发布 | ⏳ 框架待补（见 §6） |

> 说明：以上为**可运行脚手架 + 核心两线打通 + E7 全局系统**。标记为 ⏳ 的是后续迭代项，接入真实大模型密钥后 Worker 写产出与 LiteLLM 路由即可启用，无需重构。

---

## 6. 后续迭代清单（建议优先级）

1. **接真实大模型**：在 `app/llm_router.py` 填 `LiteLLMProvider.generate`（取消注释 `litellm` 调用 + 上传结果到 MinIO），改 `PEA_PROVIDER_PRIMARY/FALLBACK`。
2. **CI/质量门**：`.github/workflows` 串 lint+build+单测；补 BFF(Jest)/Orchestrator(pytest) 基线测试。
3. **可观测**：OTel SDK + Prometheus + Grafana（ARCH D11），一个生成任务全程 trace。
4. **E2E 关键链路**：上传→规划→生成→画布产出（T-OBS-02）。
5. **E5 增强**：Agent 对话面板接 LLM、富文本工具条、侧边面板、右键/快捷键。

---

## 7. 密钥与配置

所有配置走环境变量（12-factor）。BFF 见 `services/bff/.env.example`，编排器见 `app/config.py` 的 `PEA_` 前缀。
**生产务必修改**：`PEA_JWT_SECRET`、`PEA_INTERNAL_SERVICE_TOKEN`、MinIO/MySQL 凭据、外部大模型 API Key。
