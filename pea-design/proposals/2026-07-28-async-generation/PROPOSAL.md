# 生成编排器：异步完成层架构设计（兼容 sync / poll / webhook）

> 提案状态：**待评审**（尚未合入 `app/`）。
> 作者：资深开发（Senior Developer）
> 日期：2026-07-28
> 背景：2026-07-28 故障复盘——Agnes 外部超时导致视频/图片任务卡 300s+，根因是 `worker.py` 单消费者单线程、长任务（视频轮询）独占 worker 线程，把"任务存活期"和"线程存活期"绑死。本文给出彻底解耦的抽象层设计。

---

## 1. 设计目标

| 目标 | 说明 |
|---|---|
| **高并发** | 单进程单事件循环扛千~万级 in-flight 任务；并发上限不再受 OS 线程数限制 |
| **高可用** | 任务状态全部落 DB；进程崩溃重启后自动续跑；webhook 模式 in-flight 甚至不需要任何进程存活 |
| **资源最小** | 生成期间（第三方渲染中）服务端**零占线程、零轮询（webhook 模式）或极低频退避轮询（poll 模式）** |
| **第三方兼容** | 统一抽象 `sync / poll / webhook` 三种完成模式；Agnes 走 `poll`，未来支持回调的提供商自动切 `webhook` |
| **可观测** | 队列 pending、单任务耗时、各接口 P95、webhook 命中/漏触发全部有埋点 |

---

## 2. 核心抽象：完成模式（CompletionMode）

每个 provider 声明自己的完成契约。抽象层据此选择"怎么知道任务做完了"。

```
                ┌─────────────────────────────────────────────┐
                │            ProviderAdapter (抽象)            │
                │  capabilities: ProviderCapabilities          │
                │  submit(req) -> SubmitResult                 │
                │  parse_status(data) -> PollStatus   # poll用 │
                │  build_callback_url(job_id) -> str # webhook │
                └───────────────┬───────────────┬─────────────┘
                                │               │
                ┌───────────────▼────┐   ┌──────▼──────────────┐
                │  PollProvider      │   │ WebhookProvider      │
                │ (Agnes 视频/图像)  │   │ (未来支持回调的厂商) │
                │ 提交后拿 task_id   │   │ 提交时附 callback_url│
                │ 我们按状态地址轮询 │   │ 第三方主动 POST 我们 │
                └────────────────────┘   └──────────────────────┘
```

### 2.1 `ProviderCapabilities`

```python
@dataclass
class ProviderCapabilities:
    completion_mode: CompletionMode          # sync | poll | webhook
    accepts_callback: bool = False           # 提交体是否接受 callback_url 字段
    status_query_template: str | None = None # poll 模式下的状态查询地址模板
                                             # 例: "/v1/videos/{task_id}" 或 "agnesapi?video_id={video_id}"
    status_parser: Callable[[dict], PollStatus] | None = None
```

### 2.2 如何"知道第三方是否支持回调"？（直接回答你的疑问）

**结论：靠"契约声明 + 可选探测"，而不是运行时盲等。**

1. **声明式 capability（主路径）**：`ai_providers` 表新增两列——`completion_mode`(枚举) 与 `accepts_callback`(bool)。是否支持回调是**提供商的协议特性**，是接入时就必须确认的契约，应由配置声明，不该每次提交去猜。
   - Agnes 当前：`completion_mode='poll'`, `accepts_callback=False`。
   - 未来某厂商若文档写"支持 webhook"：`completion_mode='webhook'`, `accepts_callback=True`。

2. **可选探测工具 `probe_provider_capabilities()`**（首次接入第三方、文档不全时验证文档真伪）：
   - 用极小 prompt 提交一次，请求体附带一个我们控制的 `callback_url` 与状态查询地址；
   - 在 `probe_timeout_s`（如 60s）内若收到该 `callback_url` 的回调 → 确认 `webhook`；否则降级为 `poll`，并用状态查询地址验证能拉到结果。
   - 这是"接入期一次性验证"，不进生产热路径。

3. **提交期动态决策（Dispatcher）**：
   - 若 `completion_mode == webhook` 且 `accepts_callback == True` 且平台已配置 `webhook_base_url` + `webhook_secret` → 在请求体附带签名 `callback_url`：`{webhook_base_url}/api/v1/generation/webhook?job_id={job_id}&sig={hmac}`。
   - 否则（绝大多数现状）→ 走 `poll`，把 `status_query_template` + `task_id/video_id` 存进 `AsyncHandle`，交给 Completer 退避轮询。

4. **降级兜底（Safety Net）**：即便声明 `webhook`，若超过 `webhook_grace_s`（如 120s）仍未收到回调，且 provider 同时暴露状态查询地址 → Completer 自动切到轮询兜底；若连状态查询地址都没有 → 判 `failed` + 退款。绝不因"等不到回调"而永久挂起。

---

## 3. 任务状态机（JobPhase）

把"业务状态"和"第三方原始状态"解耦。DB 主表 `generation_jobs.status` 仍是 `queued → running → done/failed/refunded`（前端语义不变）；新增 `generation_task_handles` 表记录第三方异步细节与轮询调度。

```
              submit()           收到结果/失败          (failed 时)
queued ──────────────▶ running ──────────────▶ done
                             │                       (成功时)
                             │  webhook 漏触发 /
                             │  poll 超时            refund
                             └────────────────▶ failed ─────▶ refunded
```

`NormalizedStatus`（第三方原始状态归一化，供状态机内部判定）：
`PENDING`(queued) → `PROCESSING`(in_progress) → `DONE`(completed) / `FAILED`(failed)。

---

## 4. 架构总览

```
┌────────────┐   enqueue    ┌──────────────────┐  fast submit   ┌──────────────────┐
│  API       │ ───────────▶ │  Redis Stream    │ ─────────────▶ │  Dispatcher      │
│ /api/jobs  │              │  (gen:queue)     │                │  (消费即 ACK)     │
└────────────┘              └──────────────────┘                └────────┬─────────┘
                                                                            │ ① submit (ms级)
                                                                            ▼
                                                                ┌──────────────────┐
                                                                │  ProviderAdapter │──POST──▶ 第三方 (Agnes)
                                                                │  (sync/poll/wh)  │
                                                                └────────┬─────────┘
                                            Persistence:                   │
                                     AsyncHandle (DB) ◀────────────────────┘
                                         │
                         ┌───────────────┴────────────────┐
                         ▼                                ▼
              ┌─────────────────────┐          ┌─────────────────────┐
              │  Completer (async)  │          │  Webhook Endpoint   │
              │  周期扫 due 任务     │          │  POST /webhook      │
              │  退避轮询状态查询     │          │  签名校验+幂等      │
              │  (poll / 兜底)       │          │  (webhook 模式)     │
              └──────────┬──────────┘          └──────────┬──────────┘
                         │ ② 完成/失败                    │ ② 完成/失败
                         └───────────────┬───────────────┘
                                         ▼
                              ┌─────────────────────┐
                              │  finalize(job)       │
                              │  - 存结果/退款        │
                              │  - publish_event()   │──▶ Redis 事件总线 ──▶ BFF WS ──▶ 浏览器
                              └─────────────────────┘
```

**关键解耦点**：Dispatcher 只做毫秒级提交并立即 ACK，长任务（视频渲染）的"等待"被移出 worker 线程，交给 Completer 的异步事件循环或第三方的 webhook。worker 线程不再被 300s 轮询占用 → 头阻塞消除。

---

## 5. 关键流程

### 5.1 提交流程（fast submit）
1. API `POST /api/jobs` 写 `generation_jobs(status=queued)` 并入 Redis Stream。
2. Dispatcher 消费消息，**毫秒级**调用 `adapter.submit(req)`：
   - `sync`：直接拿到结果 → `finalize(done)`。
   - `poll`/`webhook`：拿到 `task_id/video_id` + 状态查询模板 → 写 `generation_task_handles`（`next_poll_at=now`，`completion_mode`）→ `db.update_job_status(running)` → 发布 `job_updated(running)` → **ACK**。
3. Dispatcher 线程立刻释放，**不等待**第三方渲染。

### 5.2 轮询完成（poll 模式，自适应退避）
- Completer 周期扫 `generation_task_handles WHERE status='processing' AND next_poll_at <= NOW()`，按批（每批 ≤50）用 `asyncio.gather` 并发 GET 状态查询地址。
- 用 `parse_status()` 归一化：`completed→DONE`（取 `url`）、`failed→FAILED`、`queued/in_progress→`更新 `next_poll_at=now+backoff(elapsed)` 继续。
- 退避策略（把固定 5s 轮询的 HTTP 负载砍 ~10 倍）：

  | 已等待 | 轮询间隔 | 理由 |
  |---|---|---|
  | 0–30s | 5–10s | 快路径，多数任务在此完成 |
  | 30–120s | 20–30s | 进入慢区，降频 |
  | 120s+ | 60s | 长任务，极少需秒级精度 |

- 超过 `video_poll_max_s` 仍未完成 → `FAILED` + 退款。

### 5.3 Webhook 完成（webhook 模式，零轮询）
- 第三方渲染完主动 `POST {webhook_base_url}/api/v1/generation/webhook?job_id=J&sig=S`。
- 端点：① HMAC 校验 `sig = hmac(job_id + provider_task_id, webhook_secret)`；② 按 `job_id` 幂等（已 done/failed 直接 200 忽略，防第三方重复投递导致重复退款）；③ `finalize(done)`。
- 全程**零轮询、生成期间不占任何服务端资源**。

### 5.4 容错 / 对账（Safety Net）
- 进程崩溃：重启后 Completer 扫 `processing` 任务续跑（DB 状态天然恢复）。
- webhook 漏触发：`completion_mode='webhook'` 且 `submitted_at < NOW()-webhook_grace_s` 且 `webhook_received_at IS NULL` → 自动切轮询兜底（若有状态查询地址）或判失败。
- 多副本：Completer 抢占用乐观锁 `UPDATE generation_task_handles SET claimed_by=uuid WHERE status='processing' AND next_poll_at<=NOW() AND claimed_by IS NULL LIMIT 50`，防双轮询。

### 5.5 通知链路（直接回答"怎么通知"）
- **第三方 → 我们**：
  - webhook 型：第三方主动 POST 我们的 `/api/v1/generation/webhook`（带签名）。
  - 轮询型：我们按状态查询地址主动拉（Agnes = `GET /v1/videos/{task_id}` 或 `GET /agnesapi?video_id=`）。
- **我们 → 前端**：**两种模式统一走现有 Redis 事件总线**——`finalize()` 发布 `job_updated(done/failed)` 与 `notification(...)`，经 BFF WebSocket 推到浏览器。前端无需感知任务到底是轮询还是回调完成的，状态语义完全一致。
- （可选增强）若 BFF 暂无 WS 推送，可加 `GET /api/jobs/{job_id}/events` 的 SSE 端点，但属于前端通道范畴，本提案不强制。

---

## 6. 配置与数据模型

### 6.1 `ai_providers` 新增列
- `completion_mode` VARCHAR(16) NOT NULL DEFAULT 'poll'
- `accepts_callback` TINYINT NOT NULL DEFAULT 0

### 6.2 新增表 `generation_task_handles`
```sql
CREATE TABLE generation_task_handles (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  job_id        VARCHAR(36) NOT NULL,
  provider      VARCHAR(64) NOT NULL,
  completion_mode VARCHAR(16) NOT NULL,          -- sync|poll|webhook
  provider_task_id VARCHAR(128) NULL,            -- Agnes task_id
  provider_video_id VARCHAR(128) NULL,           -- Agnes video_id (推荐查询结果用)
  status_query  VARCHAR(255) NULL,               -- 渲染后的状态查询 URL/路径
  phase         VARCHAR(16) NOT NULL DEFAULT 'processing',
  raw_status    VARCHAR(32) NULL,
  progress      INT NULL,
  poll_attempts INT NOT NULL DEFAULT 0,
  last_poll_at  DATETIME(3) NULL,
  next_poll_at  DATETIME(3) NOT NULL,             -- 退避调度核心
  webhook_received_at DATETIME(3) NULL,
  claimed_by    VARCHAR(64) NULL,                 -- 多副本乐观锁
  error         VARCHAR(512) NULL,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uq_job (job_id),
  KEY idx_due (phase, next_poll_at),
  KEY idx_webhook (completion_mode, webhook_received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 6.3 配置（`config.py` 追加/修改）
```python
# 决策④: 每用户并发 (Redis 共享原子计数, 取代 worker._in_flight 进程内 dict)
per_user_concurrency: int = 12                  # 原 3 -> 12
per_user_concurrency_ttl_s: int = 3600          # 兜底 TTL, 防异常未 release 永久泄漏
# 决策③: 连续失败滑动窗口告警
failure_alert_threshold: int = 5                # 近窗口内失败数达此值 -> 系统告警
failure_alert_window_s: int = 300              # 滑动窗口 5 分钟
# webhook (决策②: secret 下沉到 ai_providers.webhook_secret, 每厂商各一把)
webhook_base_url: str = ""          # 对外可达的回调基址
webhook_grace_s: int = 120          # webhook 多久没来就转轮询兜底
completer_batch: int = 50           # 每批并发查询数
completer_tick_s: int = 2           # 扫描周期
provider_http_pool: int = 200       # httpx 异步连接池上限
```

---

## 7. 并发与资源模型（为什么这是"资源最小"的正解）

- **async I/O（httpx.AsyncClient + 单 asyncio 事件循环）**：一次状态查询是 `await`，不占 OS 线程。单循环可同时 hold 数千 in-flight 查询；Completer 每 tick 只处理"到点的"那批，HTTP 并发由连接池上限（`provider_http_pool`）封顶。
- **对比旧方案**：旧 `worker.py` 一个视频轮询占 1 线程 420s（submit 120 + poll 300），并发=线程数；新方案并发=事件循环能力（万级），且生成期间除"到点那一下 GET"外不消耗服务端资源。
- **对比"多 consumer"误区**：多 worker 只是线性放大线程+RAM，仍会头阻塞、且更多并发轮询会把 Agnes 打得更狠。本方案不治标只治本。

---

## 8. 与现有代码的衔接（最小侵入迁移）

| 现有文件 | 改动 |
|---|---|
| `worker.py` | `_process()` 不再内联阻塞轮询；改为调用 `dispatcher.submit_job()`（fast），立即 ACK。删除 `_poll_video` 内联逻辑。看门狗硬超时分支**尊重 `allow_mock_fallback`**（生产超时即 `failed`，绝不回退假 URL）。每用户并发软护栏 `_in_flight` 换 Redis 原子计数。 |
| `agnes_provider.py` | 拆出 `AgnesAdapter`（继承 `BaseProviderAdapter`），`submit()` 只提交并返回 `AsyncHandle`，轮询逻辑移到 Completer。保留 `param_adapters` 防腐层。 |
| `api.py` / `main.py` | 挂载 `webhook.py` 路由；`run_forever()` 启动 `completer_loop()`（asyncio）。 |
| `config.py` | 追加 §6.3 字段。 |
| `db.py` | 追加 `finalize_job` / `claim_due_handles` / `update_handle` 等（见 `db_async.py`）。 |

---

## 9. 灰度 / 上线 / 回滚

1. **灰度**：先仅对 `type=video` 启用新异步完成层（图像保持现有同步出图，风险最小）；观察 Completer 负载与 DB 写入。
2. **开关**：`config.completion_enabled`（默认 False，走老路径）；切 True 后新任务走新层。
3. **回滚**：开关置 False + 重启 worker 即可回老逻辑；已在新层的 in-flight 任务由老 worker 无法接管，但 DB 状态仍可被手动脚本兜底（极少发生）。
4. **验证**：用 `probes` 脚本单发一个视频任务，观察 `generation_task_handles` 行从 `processing`→`done`、`next_poll_at` 退避递增、事件总线收到 `job_updated(done)`。

---

## 10. 决策记录（2026-07-28 用户拍板）

- **① 结果转存：做。** `finalize_job` 成功时调用现成的 `storage.store_from_url`，把 Agnes 临时 URL 转存到自有 MinIO，返回稳定 CDN URL 给前端；转存失败降级用原始 URL + 告警（不因存储抖动拖垮生成）。彻底解决"公网 URL 过期 403"。
- **② webhook secret：每厂商各一把。** 已下沉到 `ai_providers.webhook_secret`（迁移脚本加列），`webhook.py` 校验时按 `provider_name` 取各自 secret，不再用全局 `settings.webhook_secret`。接第二家厂商时互不干扰。
- **③ 失败判定 + 告警。** 失败判定 = 通过任务 ID 查状态返回 `failed` → 立即停查（completer 已实现：命中 `FAILED` 置终态，`claim_due_handles` 只捞 `phase='processing'`，failed 后不再被查）。告警 = 近 5 分钟连续 5 个任务失败触发系统级 warning 通知（Redis 滑动窗口，见 `dispatcher._record_failure`），让"链路又挂了"1 分钟内被发现而非用户投诉。
- **④ 每用户并发：Redis 共享原子计数，上限 12。** 新增 `concurrency.py` 取代 `worker._in_flight` 进程内 dict；`config.per_user_concurrency` 由 3 改为 12；`acquire/release` 配对收口在 `dispatcher.submit_job` / `finalize_job`，多副本下真正限得住。

---

## 11. 实现文件清单（见同目录）

| 文件 | 职责 |
|---|---|
| `app/async_core/__init__.py` | 包导出 |
| `app/async_core/types.py` | CompletionMode / NormalizedStatus / ProviderCapabilities / AsyncHandle / PollStatus / SubmitResult |
| `app/async_core/provider_adapter.py` | 抽象 `BaseProviderAdapter` + `AgnesAdapter`(poll) + `WebhookCapableMixin` |
| `app/async_core/backoff.py` | 自适应退避 `next_interval(elapsed)` |
| `app/async_core/state_machine.py` | JobPhase 转换规则 |
| `app/async_core/dispatcher.py` | fast submit + 写 AsyncHandle + ACK |
| `app/async_core/completer.py` | async 轮询回路 + 对账兜底 |
| `app/async_core/webhook.py` | FastAPI webhook 路由（签名+幂等） |
| `app/async_core/db_async.py` | handles 表读写 + 抢占查询 |
| `migrations/002_async_handles.sql` | DDL |

> 这些文件当前放在提案目录，确认后整体移入 `services/generation-orchestrator/app/async_core/` 并改 `worker.py` / `main.py` / `config.py` / `db.py` 接线。
