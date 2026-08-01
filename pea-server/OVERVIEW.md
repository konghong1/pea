# pea-server 交付概览（2026-07-22）

> 资深开发工程师（吴八哥）按架构/PRD/任务拆解落地 pea Creative OS 首版可运行脚手架，
> 重心打通**生成异步管道 + 积分双记账本 + 画布自动保存**三条 Now 阶段主线。

## 交付内容

### 1. 品牌重命名（tapnow → pea）
- 设计文档目录 `tapnow/` → `pea-design/`，全项目字符串 `tapnow` → `pea`（含 HTML 原型、i18n bundle、配置）。
- 代码仓库命名 `pea-server/`，全项目零 tapnow 残留（已 grep 校验）。

### 2. 工程基座（E0 / T-INFRA）
- `docker-compose.yml`：一键起 MySQL 8 + Redis 7 + MinIO + BFF + Orchestrator + Web（含 healthcheck 依赖）。
- `infra/mysql/init/01-schema.sql`：MySQL 8 DDL，**幂等**，含 JSON 列、生成列索引（`node_count`）、`ledger_entries` 按月 RANGE 分区、`accounts.version` 乐观锁、`v_user_balance` 视图。
- 三个 Dockerfile + nginx 反代（Web 静态资源 + API/WS 代理到 BFF）+ Makefile。

### 3. BFF（NestJS）
- `auth`：注册/登录，JWT，新用户赠 1000 Tapies。
- `billing`：余额查询、流水、**双记账本预扣/确认/退还事务**（`txn_id` 幂等 + `version` 乐观锁强一致）、内部退款接口（service token 鉴权）。
- `generation`：受理接口（校验→预扣→返 jobId，p95<2s 设计）、状态/历史代理到编排器。
- `files`：S3 预签名直传 + 强制签名访问。
- `canvases`：建/存/取，**自动保存 + 乐观锁 409 冲突**。
- `gateway`：WebSocket（`/ws`），订阅 Redis 事件按用户推 `job.updated`/`balance.changed`/`notification`。
- 全局：异常过滤器、校验管道、限流中间件。

### 4. 生成编排器（FastAPI）
- `models.py`：状态机 `queued→running→done/failed→refunded`（非法跳转拒绝）。
- `redis_conn.py`：Redis Streams 队列（普通/极速）+ 事件发布。
- `worker.py`：消费队列→调模型→回写→发布事件；每用户并发软护栏；失败→补偿退款。
- `async_core/provider_adapter.py`：**统一 Provider 适配器抽象**（`BaseProviderAdapter`），按 `provider_type` 走 `AgnesAdapter`(OpenAI 兼容, 视频异步轮询) / `MockAdapter`(本地占位)；`GenerationResult` 收编至 `async_core/types.py`。原 `llm_router.py` 已合并删除。
- `compensation.py`：失败经 BFF 内部退款。
- `api.py`：受理/查询（生成域拥有者）。

### 5. Web（React + Vite + ReactFlow + Zustand + antd）
- 登录/注册、顶栏余额 + **浅/深/跟随 三态主题**。
- 画布编辑器：节点/连线/小地图、Inspector、**防抖自动保存**、生成节点「⚡生成」接入管道 + WS 实时进度。

### 6. 跨服务契约
- `services/shared/events.ts` 与 `events.py` 双镜像，定义 Redis 事件协议（改一侧必同步另一侧）。

## 验证情况
- ✅ Python 语法编译通过（`py_compile`）。
- ✅ `docker compose config` 校验通过。
- ✅ 所有 JSON 配置解析通过。
- ⚠️ 实际 `docker compose up --build` 需联网拉取依赖（npm/pip）并依赖 Docker daemon；本环境未执行完整构建（Docker 正在迁移路径），按文档本地/容器均可一键起。

## 下一步（建议）
1. 接真实大模型（填 `LiteLLMProvider.generate` + 改 `PEA_PROVIDER_*`）。
2. 补 CI / 单测基线（Jest + pytest）/ E2E。
3. OTel + Prometheus + Grafana 可观测。
4. E5 增强（Agent 对话面板、富文本）、E7 Toast/分享、E8/E9 主页与社区。

详见 `README.md`。
