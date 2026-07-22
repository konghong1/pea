# pea Creative OS — 核心子系统设计（10 万用户量级）

> 配套：`PRD-pea-Creative-OS.md` / `ARCH-pea-Final.md`（架构终稿） / `ROADMAP-pea-Creative-OS.md`
> 版本：v1.0　角色：软件架构师　日期：2026-07-22
> 状态：Proposed — 待技术评审

本文把架构文档里"三句话带过"的三个重心 + 用户追问的文件存储，落到**可实现的详细设计**，并明确按 **~10 万注册用户** 量级做容量规划。所有大数都是**带假设的推算**，正式设计前用真实业务数据校准。

---

## 0. 10 万用户容量模型（所有设计的规模基线）

| 维度 | 假设值 | 说明 |
|---|---|---|
| 注册用户 | 100,000 | 设计目标量级 |
| DAU | 20,000（20%） | 内容创作产品典型留存 |
| 峰值在线并发 | ~2,000 | 晚高峰同时在线 |
| 日生成任务 | ~6,000（DAU 的 30%） | 图像 85% ≈ 5,100；视频 15% ≈ 900 |
| 生成峰值速率 | ~2 任务/秒（写入） | 黄金 4h 集中，峰值 3–5x |
| 视频任务时长 | 平均 3 分钟 | GPU 长任务，占 worker |
| 图像任务时长 | 平均 15 秒 | |
| 画布存储 | 100k×3 画布×200KB ≈ **60 GB** | 小，MySQL 无压力 |
| 生成媒体 | 100k×500MB ≈ **50 TB**（含视频） | 必须用生命周期压成本 |
| 用户上传图 | 100k×5×2MB ≈ **1 TB** | |
| 积分流水 | ~12k 行/日（双记）≈ **440 万行/年** | 按月分区轻松 |

**推算结论（先给结论，后文展开）**：
- 生成 Worker 池：视频 GPU worker ~20–30 并发，图像 ~10–15 并发（弹性）。**远不到"天文数字"**，但必须异步 + 弹性，否则视频任务直接打死请求线程。
- DB：单主 + 1 读副本 + PgBouncer 连接池即可扛 10 万；ledger 表按月分区。
- 存储：S3 + 生命周期是唯一经济解，没有之二。

---

## 1. 生成异步解耦（Generation Async Decoupling）

### 1.1 设计原则
- **同步路径只做三件事**：校验 → 预扣积分 → 建 Job 返回 `jobId`，全程 < 2s（PRD NFR）。
- **重活在异步 Worker**：真正的模型调用、轮询、回调、落库全在 Worker，绝不占 API 线程。
- **调用方拿到的是"受理回执"不是"结果"**：前端用 `jobId` 经 WS/SSE 订阅状态。

### 1.2 组件与数据流（时序见文末图）
```
[Web] ──POST /generate──▶ [API/BFF] ──(1)校验+预扣积分(saga)──▶ [DB: Job=queued]
                                  │                                │
                                  │                                ▼
                                  │                         [Queue: 优先级]
                                  │                                │
                                  │                         [Orchestrator]
                                  │                                │ 选 Adapter + 路由
                                  ▼                                ▼
                         返回 {jobId} ◀─── [Worker] ──▶ [Provider(MJ/Kling/...)]
                                                          │ 超时/重试/断路器
                                                          ▼
                                                  [S3 存媒体] ─▶ [Job=done]
                                                                  │ 发事件"生成完成"
                                                                  ▼
                                                          [WS/SSE 推前端]
                                                          [社区/通知 消费事件]
```

### 1.3 任务状态机
```
queued ──▶ running ──▶ done
   │           │
   │           └──▶ failed ──▶ (补偿退还积分, Job=refunded)
   └──(超时未取) ──▶ expired
running 超时未心跳 ──▶ failed
```
- 每个 Worker 处理中须定期回报心跳（如每 30s），Orchestrator 对超时无心跳的 Job 判 failed 并重投（最多 N 次）。

### 1.4 队列 / 优先级 / 限流 / 回退 / 断路器
- **优先级**：`极速`(电商付费加速) 走高优队列；普通走默认队列。队列用 Temporal Task Queue 或 Redis Streams 多 consumer group。
- **每用户限流**：令牌桶（Redis）限制单用户并发生成数（如 ≤5）+ 日额度，防单用户打爆成本（ARCH 终稿 §9 风险 1）。
- **Provider 限流/预算**：路由层对每 Provider 设 QPS 上限 + 日预算上限，超限熔断并回退。
- **回退**：按用户 Provider 配置（PRD §5.4），默认项失败 → 下一个启用项；全失败时 Job=failed + 退还积分。
- **断路器**：某 Provider 连续错误率超阈值 → 临时摘流，半开探测恢复。

### 1.5 数据模型（关键字段）
```sql
generation_jobs (
  id UUID PK,
  user_id,
  type ENUM(image/video/audio/world3d/replace),
  model VARCHAR,                 -- 实际选用（回退后）
  status ENUM(queued,running,done,failed,refunded,expired),
  priority ENUM(normal,fast),
  points_preempted INT,          -- 预扣积分
  idempotency_key VARCHAR UNIQUE,-- 防重复扣费
  provider VARCHAR,
  attempt INT DEFAULT 0,
  result_url VARCHAR,            -- S3 对象 key
  error TEXT,
  created_at, updated_at
);
CREATE INDEX ON generation_jobs(user_id, status);
```
- **幂等**：`idempotency_key` 唯一约束，API 层先查后建，重复提交直接返回原 `jobId`，**绝不二次扣费**。

### 1.6 容量与扩缩（10 万）
- 视频 ~900/日，峰值并发 ~12 → 视频 GPU worker 池 **20–30**（含 buffer 与弹性）。
- 图像 ~5,100/日，峰值并发 ~6 → 图像 worker 池 **10–15**。
- K8s 按模型类型独立 **node pool**（image/video/audio/3d），HPA 按队列深度自动扩缩；GPU 节点用 spot/抢占式降成本。
- 队列深度监控 + 背压：深度超阈值时 API 直接拒绝新提交并提示"系统繁忙"，而非无限堆积。

### 1.7 失败补偿（与积分联动）
- Job=failed/timeout → 触发补偿事务：按 `points_preempted` 记一笔 **credit（退还）**，Job=refunded。
- 补偿必须**幂等**（同 jobId 只退一次），否则会"退两次"。

### 1.8 可观测
- 每 Job 一个 `traceId` 贯穿 API→Queue→Worker→Provider→S3。
- 指标：生成成功率、P95 时长(分类型)、Provider 错误率、队列深度、积分异常率、单位成本。
- 告警：成功率 < 95%、队列深度突增、单用户花费 > 预算 3x。

### 1.9 权衡与开放问题
- **取舍**：异步带来"结果异步到达"的复杂度（WS/SSE + 状态轮询兜底），换来 API 不被打死 + 可弹性扩缩。这是必选项，不是优化项。
- **开放**：Worker 用 Temporal 还是 Celery？Temporal 自带重试/补偿/可观测，强烈推荐但学习曲线陡（已在 ROADMAP Next 阶段引入）。Now 阶段可用 Celery + 手写补偿先跑通。

---

## 2. 积分双记账本（Points Double-Entry Ledger）

### 2.1 设计原则
- **每笔变动记借贷两行**：`debit`（出）+ `credit`（入），余额 = Σ 所有行净变动。
- **预扣即在事务内完成**：生成前减可用余额，失败补偿加回，绝不"先生成后算账"。
- **强一致**：钱包是系统里最不能错的地方，走 ACID + 行锁 + 每日对账。

### 2.2 数据模型
```sql
accounts (                       -- 每用户一行
  user_id PK,
  balance INT NOT NULL DEFAULT 0,   -- 当前积分（整数，避免浮点）
  version INT NOT NULL DEFAULT 0,   -- 乐观锁
  updated_at
);

ledger_entries (                 -- 双记账流水（按月分区）
  id BIGSERIAL,
  txn_id VARCHAR UNIQUE,         -- 幂等键（同 txn 不重复入账）
  user_id,
  direction ENUM(debit, credit), -- 借/贷
  amount INT,                    -- 正整数
  balance_after INT,             -- 该行后余额（便于核对）
  ref_type ENUM(generation_preempt, generation_confirm,
               generation_refund, recharge, subscription...),
  ref_id VARCHAR,                -- 关联 job_id / order_id
  created_at
);
CREATE INDEX ON ledger_entries(user_id, created_at);
```

### 2.3 预扣 / 确认 / 退还 流程（同一事务 + 行锁）
```
生成受理（API 内事务）:
  BEGIN;
  SELECT balance FROM accounts WHERE user_id=? FOR UPDATE;  -- 行锁防竞态
  IF balance < cost THEN ROLLBACK + 拒绝;
  balance -= cost;  version++;
  INSERT debit  (txn=preempt, -cost, balance_after);
  COMMIT;
  → 返回 jobId

生成成功（Worker 回调）:
  仅"标记"该预扣为已消费（可写 confirm 行或更新 ref 状态），无需再动余额。

生成失败（补偿事务）:
  BEGIN;
  SELECT ... FOR UPDATE;
  balance += cost;  version++;
  INSERT credit (txn=refund, +cost, balance_after);
  COMMIT;
  Job=refunded;
```
- **幂等**：`txn_id` 唯一；预扣与退还使用不同 txn 前缀但都基于 `jobId`，补偿侧查"该 job 是否已退"防止重复退。

### 2.4 一致性与性能（10 万）
- **行锁**保证单用户并发扣减不出错（如用户同时点两次生成）。
- **余额热点**：余额读多写少 → Redis 缓存 `balance:{user_id}`，写入时 **先更 DB 再删缓存**（Cache-Aside）；读未命中回源。缓存击穿用单飞(singleflight)。
- **分区**：`ledger_entries` 按月 RANGE 分区，年增量 440 万行无压力，历史查询走分区裁剪。
- **是否分库分表**：10 万用户单实例足够，**暂不分片**；等 DAU/流水再上一个量级再评估（可逆，先留 `user_id` 哈希分片余地）。

### 2.5 每日对账（防错账兜底）
- 定时 job：对每用户 `SUM(ledger_entries 净变动)` 对比 `accounts.balance`，不一致告警 + 自动修复（以流水为准重算余额）。
- 这是"双记账 + 行锁"之外的最后一道保险，成本极低。

### 2.6 权衡
- **写入量翻倍**（每笔两行）——可接受，换来"永远算得清"。
- **开放**：积分是否过期？是否区分"赠送/购买"不可混用？涉及合规与财务，需 PRD/法务确认（列入开放问题）。

---

## 3. 画布自动保存（Canvas Autosave）

### 3.1 设计原则
- **默认不丢**：解决 PRD 标红的"原型刷新即丢"痛点（P0）。
- **低摩擦**：debounce ~1s + 失焦(blur) + `beforeunload` 强制刷一次；不打断创作。
- **单人优先**：Now 阶段单人编辑，用版本号乐观锁即可；协作(CRDT)进 Later（ROADMAP）。

### 3.2 写入路径
```
[画布变更] ──debounce 1s──▶ [组装 payload: {nodes, edges, zoom, pan, version}]
        │
        ▼
PUT /canvas/:id  {version: N}
        │
        ├─ 服务端: SELECT version WHERE id=? FOR UPDATE
        │   version == N  → 写新图, version=N+1, lastModified=now  → 200
        │   version != N  → 409 Conflict（另一标签/设备已改）
        │       └─ 客户端: 拉最新 + 提示"内容已变更，是否覆盖/合并"
        ▼
   前端存本地草稿(IndexedDB) 作为离线兜底，重连后 diff 上传
```

### 3.3 存储
- **主存**：`canvases` 表，节点图/连线存 **JSON**（`nodes json, edges json`），`version INT`, `lastModified`。
- **版本历史（侧边面板"历史记录"）**：`canvas_versions` 追加表（`canvas_id, version, snapshot json, op_log json, created_at`），按 `canvas_id` 分区或限长（如保留最近 50 次）。操作日志对应 PRD 侧边面板 FR-M1-62。
- **容量**：100k×3×200KB ≈ 60GB，MySQL 轻松；JSON 列建生成列索引仅当需按节点内容检索时（一般不必）。

### 3.4 容量与性能（10 万）
- 写入频率被 debounce 压到"每画布 ~1 次/秒峰值"，10 万用户并发编辑但分散 → DB 写入 QPS 可控（千级）。连接池 + 批量/异步 flush。
- 可选优化：热画布先写 **Redis 工作副本**，每数秒异步落 MySQL；但 Now 阶段直接落 MySQL 更简单，先不做。
- 大画布（>200 节点，PRD §6.4 预警）：整图上传可能数百 KB，debounce + 必要时增量 diff（节点级 patch）降本。

### 3.5 多标签页 / 离线
- 多标签同账号：靠 `version` 乐观锁 + 409 解决冲突（简单、够用）。
- 离线编辑（PRD §13 开放问题）：本地 IndexedDB 草稿，恢复网络后 diff 上传；真正的 CRDT 协作 Later 再做。

### 3.6 权衡
- **整图版本号 vs OT/CRDT**：Now 用整图+版本号，实现简单、冲突处理清晰；代价是"整图覆盖"而非字段级合并。协作需求明确后再上 CRDT（Yjs），届时有架构余量。

---

## 4. 文件存储（File Storage）—— 用户追问的部分

> 架构文档只写了"S3 兼容 + 生命周期"，这里补齐完整设计。

### 4.1 架构
```
[用户上传] ──▶ 预签名 PUT URL ──▶ [S3 直传]        (不经过 API，省带宽/线程)
[Worker 产出] ──▶ SDK PUT ──▶ [S3]
        │
        ▼
[S3 对象] ──生命周期策略──▶ [IA / Glacier / 删除]
        │
        ▼
[CDN 边缘] ◀── 签名 URL 访问（防跨用户泄露）
```
- **对象存储**：S3 兼容（云 OSS / MinIO）。**不用本地磁盘**，天然多副本 + 生命周期。
- **CDN**：所有媒体读走 CDN，降低源站压力与延迟。

### 4.2 上传流程（两类来源）
- **用户产品图上传**：前端向 API 要**预签名 URL**（带过期 + 前缀限制），浏览器**直传 S3**，完成后回传 object key 给后端登记（写 `product_images`）。API 不碰字节，省资源。
- **生成产出**：Worker 直接 SDK 写 S3，写完后把 object key 存 `generation_jobs.result_url`，发"生成完成"事件。

### 4.3 租户隔离与签名访问
- **Key 命名**：`s3://{bucket}/{env}/{tenant_id}/{type}/{uuid}.{ext}` —— 前缀即隔离边界。
- **访问强制签名 URL**：任何媒体读取都走后端签发的有时效 URL（如 15min），**绝不暴露永久公开链接**，杜绝跨用户泄露（PRD NFR / 个人信息保护法）。
- **删除**：用户删资源 → 软删 DB 记录 + 异步删 S3 对象（或标记过期由生命周期清理）。

### 4.4 生命周期与成本（10 万量级核心）
- 生成媒体（尤其视频）体积大：
  - 7 天内：标准存储（热访问）。
  - 30 天后：转 **IA（低频）** 或 **Glacier（归档）**。
  - 180 天 / 用户注销：清理（或按套餐保留）。
- 估算：50TB 热转冷可降存储成本 60–80%；配合用户配额（如免费版累计 5GB）控总量。
- **去重**：上传产品图按内容哈希去重，同图只存一份。
- **缩略图/转码**：图像生成多分辨率变体、视频抽帧预览，异步 worker 产出，原片归档。

### 4.5 容量估算（10 万）
| 类型 | 估算 | 策略 |
|---|---|---|
| 用户上传图 | ~1 TB | 标准 + 去重 |
| 生成媒体 | ~50 TB（含视频） | 生命周期冷归档 |
| 画布 JSON | ~60 GB | MySQL |
| **S3 总费用大头** | 生成媒体 | 生命周期 + 配额是省钱关键 |

### 4.6 备份 / 合规
- 关键 bucket 开 **版本控制** + 跨区复制（用户上传原图不可丢）。
- 生成媒体可容忍重生成 → 可不跨区复制，靠生命周期。
- 上传文件做**病毒/违规扫描**（异步），命中即隔离 + 通知。
- 用户注销：按合规要求保留期后彻底清理（含 S3）。

### 4.7 权衡
- **预签名直传**省 API 资源，代价是"上传完成"需前端回传确认（可能丢，需超时补偿/校验）。
- **签名 URL**保安全，代价是每次读要多一次签发（可短缓存）。

---

## 5. 跨系统一致性（四者如何协作）

一次"电商套图生成"把四个子系统串起来：
```
1. [画布/电商配置] 落库（自动保存）
2. [API] 预扣积分（ledger 事务，得 jobId）          ── 区块1
3. [Queue→Worker] 调 Provider 生成                  ── 区块2（异步）
4. [Worker] 媒体写 S3（文件存储）                    ── 区块3
5. [Worker] Job=done + 发"生成完成"事件
6. [补偿] 若失败 → ledger 退还 + Job=refunded
7. [前端] WS/SSE 收状态 → 画布/结果区更新
```
- **一致性边界**：积分(强一致) 与 媒体/社区(最终一致) 分离；只有"预扣+退还"走事务，其余靠事件 + 补偿。
- **失败注入想清楚**：Provider 超时 / S3 写失败 / WS 断线 分别怎么收场？—— 见各 §的失败处理。

---

## 6. 资源容量总览（10 万假设）

| 资源 | 规模 | 备注 |
|---|---|---|
| MySQL | 1 主 + 1 读副本 + 连接池 | ledger 按月分区 |
| Redis | 1 主 + 副本（哨兵/集群） | 限流/缓存/WS PubSub |
| 队列/编排 | Temporal 或 Celery+Redis | Now 可 Celery 起步 |
| 生成 Worker | 视频 20–30 / 图像 10–15 并发池 | K8s HPA 弹性，GPU spot |
| 对象存储 | S3 + 生命周期 + CDN | 50TB 媒体靠冷归档 |
| 可观测 | OTel + Prometheus + Grafana | 每 Job traceId |

---

## 7. 开放问题（需拍板）
1. Worker 编排 Temporal vs Celery（影响 Now 实现复杂度）。
2. 积分是否过期 / 赠送与购买是否隔离（财务/合规）。
3. 画布是否需要离线编辑 SLA（决定 IndexedDB 投入）。
4. 用户媒体配额（免费/付费）具体数值（影响存储成本上限）。
5. 视频生成是否限制单用户并发与日额度（影响成本护栏力度）。

---

*本设计为基于 PRD/ARCH/ROADMAP 的详细基线，容量数字为假设推算，落地前用真实业务数据校准，并经技术评审确认 ADR（生成异步 ADR-002 / 双记账本 ADR-006 / React Flow ADR-003）。*
