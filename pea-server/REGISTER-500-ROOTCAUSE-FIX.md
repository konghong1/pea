# 注册 500 故障 — 根因复盘与根治报告

> 处理人角色：Senior Developer（高级开发工程师）
> 日期：2026-07-24
> 影响：所有新用户无法通过 `http://localhost:8088/auth/register` 注册

---

## 一、现象
- 用户访问 `http://localhost:8088/auth/register`（前端入口，反向代理到 BFF `:4100`）提交注册，返回 `500 internal error`。
- 直接打 BFF `POST /auth/register` 同样 `500`。
- 已有账户登录正常，说明问题只在**注册写流水**这一步。

## 二、根因（不是猜的，是查出来的）
**Docker 持久卷 DDL 陷阱**导致的运行库 schema 漂移：

1. 源码 `infra/mysql/init/01-schema.sql` 里 `ledger_entries.type` 已是
   `ENUM('grant','preauth','confirm','refund')`。
2. 但 MySQL 用的是 **named volume**（`mysql_data`），容器重启**不会重跑**
   `/docker-entrypoint-initdb.d` 下的初始化脚本——只在**首次建卷**时跑一次。
3. 后续有人把 `'grant'` 加进 DDL（对应 `auth.service.ts` 注册时要插一行
   `type='grant'` 的开户赠金流水，作为余额对账基准），但已有卷没跟上。
4. 真机核查运行库：`ledger_entries.type` 实际只有 `('preauth','confirm','refund')`，
   **缺 `'grant'`**。注册时 `INSERT ... type='grant'` 落到一个不存在的枚举值上 → MySQL 报错 → BFF 抛 500。

> 一句话：代码要写 `'grant'`，数据库却不认这个值。

## 三、止血（立即生效）
在运行库执行（已做）：
```sql
ALTER TABLE pea.ledger_entries
  MODIFY COLUMN type ENUM('grant','preauth','confirm','refund') NOT NULL;
```
验证：经 `8088` 与 `4100` 注册均返回 `201` + JWT，登录联动正常。

## 四、根治（防复发，T-OBS-04 真正落地）
光改运行库是治标——下次 `docker compose down/up` 或换机器，漂移还会回来。
所以做了**自愈护栏**：

1. **新增 `infra/mysql/assert-migrated.sh`**
   - 启动期幂等自检：等待 MySQL 就绪 → 断言 `ledger_entries.type` 含 `'grant'` →
     缺失则自动 `ALTER` 补回，已正确则跳过。
   - 后续任何 DDL 变更，在此追加一条断言即可，无需人工记着去 ALTER。

2. **`docker-compose.yml` 加 `dbmigrate` 一次性服务**
   - 用 `mysql:8.0` 镜像跑上面的脚本，`restart: "no"`，跑完即退出。
   - `bff` 与 `generation-orchestrator` 的 `depends_on` 增加
     `dbmigrate: condition: service_completed_successfully`。
   - 效果：**每次 `docker compose up` 都会先自检并自愈 DDL 漂移，再起业务服务。**

**验证（trust but verify）：**
- 已正确态下跑 `dbmigrate` → 检测 OK、退出 0，不破坏服务。
- 用独立测试表（缺 `grant`）跑同一脚本 → FIX 分支被触发、枚举自动补全。
- 故意模拟漂移 → 脚本 + 容器编排能自愈。

## 五、给团队的代码质量建议（借这次故障）
1. **DDL 变更必须成对提交**：改 `01-schema.sql` 的同时，在 `assert-migrated.sh`
   加对应断言。把“要不要手动 ALTER”从人脑里摘掉，交给启动时自检。
2. **BFF 别裸抛 500**：当前全局异常过滤把 DB 错误吞成 `internal error`，
   前端完全无法区分根因。建议注册失败显式捕获、返回结构化错误码
   （如 `LEDGER_WRITE_FAILED`），非生产环境日志打印原始 stack——能省下这次
   一半的排查时间。
3. **环境一致性**：本地用 named volume 持久化，CI/生产用迁移工具（如
   migrate/Atlas）。至少保证“本地一键起”和“他人 clone 后一键起”看到的是同一套 schema。
4. **E2E 要覆盖注册这个关键路径**：现有 `verify/verify_e*.py` 偏画布交互，
   建议在冒烟脚本里加一条“注册→登录→查余额=1000”的断言，这类后端写故障
   能在 PR 阶段就暴露，而不是等用户报。

## 六、改动清单
| 文件 | 改动 |
|------|------|
| `infra/mysql/assert-migrated.sh` | **新增**：DDL 漂移幂等自检脚本 |
| `docker-compose.yml` | **新增** `dbmigrate` 服务；`bff`/`generation-orchestrator` 增加对其 `depends_on` |
| 运行库 `ledger_entries.type` | **已 ALTER** 补回 `'grant'` 枚举值 |

> 注：DDL 文件 `01-schema.sql` 本身无需改（早已正确），问题只在“持久卷不重跑”。
