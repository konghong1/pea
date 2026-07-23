# pea Creative OS — 资深开发代码质量评审与整改报告

> 评审人: Senior Developer (高级开发工程师) · 日期: 2026-07-23
> 范围: `pea-server/` 全部后端 + 生成编排器 + 任务追踪表/README 失真
> 结论: **脚手架功能基本具备, 但"钱路"(记账本)存在严重并发/正确性缺陷, 且质量门(E10)完全缺失、任务追踪表与代码实际状态严重脱节。** 本期已修复钱路正确性 + 立起质量门基线。

---

## 一、最严重的问题: 任务追踪表自身失真(治理问题)

- **TASK-BREAKDOWN §3 矩阵** 把 E0–E5 大量任务标 `未开始`, 但代码里这些模块**真实存在且可运行**(auth/billing/generation/canvas/files 均有实现)。
- 同一张表又把 E7/E8/E9 标 `已验证(Playwright 可视化验证 0 报错)`——**而仓库里没有任何测试/CI 工具链**, 这些"已验证"是**假的**。
- 矩阵内部自相矛盾: `T-G-01`(开发完成) 依赖 `T-M1-01`(未开始), 不可能成立。
- **资深开发判断**: 任务追踪表作为"唯一事实源"已失信, 比代码 bug 更危险——它会让团队误判进度、在"以为已验证"的功能上继续堆代码。已在校正版 §3 矩阵中全部修正(见 `TASK-BREAKDOWN-pea.md`)。

---

## 二、钱路(记账本)正确性缺陷 — 已修复

| # | 缺陷 | 原来代码 | 风险 | 修复 |
|---|---|---|---|---|
| 1 | **幂等校验在行锁之前** | `preauthorize`/`refund` 先 `SELECT txn_id` 再 `FOR UPDATE` | 并发同 `txn_id` → **双扣/双退** | 改为**先 `FOR UPDATE` 再查幂等**(分区表唯一键含 `created_at`, DB 无法单独约束 txn_id, 必须在锁内校验) |
| 2 | **注册不写赠金流水** | `auth.service` 直接 `balance=1000`, 无 ledger 行 | `balance != Σcredit−Σdebit`, **永远无法对账** | 注册事务内写 `grant` 贷方流水(枚举已加 `'grant'`) |
| 3 | **"乐观锁"是假的** | `version=version+1` 无 `WHERE version=?`、无 affectedRows 校验 | 纯装饰, 并发靠 `FOR UPDATE` 串行 | 明确改用**悲观行锁**(钱路人热点, 悲观锁比乐观锁重试更稳); `version` 仅作审计序号。README/ARCH 的"乐观锁"表述已更正 |
| 4 | **预扣未 await** | `this.billing.preauthorize(...)` 没 `await` | 下游失败 → 积分已扣却无退款 → **白送** | 改为 `await`; 受理失败本地立即退款(`${idem}:refund`), 与编排器退款(`${job_id}:refund`)不同键不冲突 |
| 5 | **退款无重试** | `compensation` 失败仅 `print` 返回 | BFF 抖动 → **永久丢钱** | 加重试 + 指数退避(上限 3 次/10s); 穷尽后交每日对账脚本兜底 |
| 6 | **退款后状态不翻转** | job 永远停在 `failed` | `refunded` 终态形同虚设 | 退款成功后 `update_job_status → refunded`(FAILED→REFUNDED 合法) |

对账不变量 `balance == Σcredit − Σdebit` 现已成立(单测 `billing.service.spec.ts` 末条断言)。

---

## 三、生成状态机 — 已修复

- `db.update_job_status` 原是直接 `UPDATE`, **非法跳转(如 `done→refunded`、`queued→done`)一律放行**。
- 现强制调用 `models.can_transition`, 非法跳转抛 `ValueError`; 同状态幂等不报错。
- 配套单测 `test_state_machine.py` 覆盖合法/非法跳转与幂等。

---

## 四、安全/越权 — 已修复

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | **文件预签名不绑定用户**: `presignPut/Get` 接受任意 `key`, 可读他人资源(违反 PRD "参考图不跨用户泄露") | 强制 `key` 位于调用者命名空间 `u:<userId>/`; 越界即 403。控制器已传 `@CurrentUser().sub` |
| 2 | **硬编码默认密钥**: `PEA_JWT_SECRET`/`PEA_INTERNAL_SERVICE_TOKEN` 默认 `'change-me-in-prod'` | 生产环境(`NODE_ENV=production`)缺失即**启动失败(fail-fast)**; 本地开发保留显式不安全默认值 |

---

## 五、E2E 分页缺陷 — 已修复

- `orchestrator /api/jobs` 接受 `cursor` 却**从未用于 SQL**, `next` 用 `cursor+limit` 伪造 → 深翻/漏页。
- 改为真实 keyset 分页(`created_at < cursor`), BFF 全链路透传时间戳游标(向后兼容前端 `cursor=0`)。

---

## 六、质量门(E10)— 本期补齐基线

| 项 | 原来 | 现在 |
|---|---|---|
| 单测基线 (T-OBS-01) | 无 | BFF Jest 测记账本逻辑(5 例) + Orchestrator pytest 测状态机/补偿(8 例), **全绿** |
| CI (T-INFRA-04) | 无 | `.github/workflows/ci.yml`: push/PR 触发, BFF 构建+单测 + Orchestrator 单测 |
| 每日对账 (T-ACC-04) | 声称"有脚本"但**仓库无** | 新增 `scripts/reconcile_ledger.py`, 余额漂移退出码 1 供告警 |

> 仍待补(下期): 真实 MySQL 并发压测(E2E)、性能基准(E2E/压测)、发布流水线灰度回滚、安全合规扫描。

---

## 七、给团队的工程规范(把关要点)

1. **钱路改动必须有测试**: 任何涉及 `accounts`/`ledger_entries` 的 PR 必须附带单测, 且**单测 + 集成压测**双覆盖并发路径。
2. **状态机/幂等是硬约束**: 锁内校验幂等; 状态流转只能走 `can_transition`; 退款必须可重试 + 对账兜底。
3. **"已验证"必须可复现**: 没有 CI/Playwright 跑通就不能写 `已验证`。任务追踪表与 git MR 一一对应, 合并即更新矩阵。
4. **密钥零默认值**: 生产密钥缺失即启动失败, 不靠"看起来能跑"。
5. **跨服务契约单一源**: `services/shared/` 的 TS/Python 事件契约改一侧必须同步另一侧(本次未动, 但列为红线)。

---

## 八、本期交付物清单

- 修复: `billing.service.ts` / `auth.service.ts` / `generation.service.ts` / `files.service.ts` + controller / `configuration.ts` / orchestrator `db.py` `worker.py` `compensation.py` `api.py` / `01-schema.sql`(加 `grant` 枚举)
- 测试: `services/bff/test/billing.service.spec.ts`(Jest) / `services/generation-orchestrator/tests/*.py`(pytest) / `jest.config.js` / `pytest.ini` / `requirements-dev.txt`
- 质量门: `.github/workflows/ci.yml` / `scripts/reconcile_ledger.py`
- 治理: `TASK-BREAKDOWN-pea.md` §3 矩阵校正 / `README.md` §5 表述更正

> ⚠️ **数据库迁移提示**: 若你已有 `mysql` 数据卷, 需手动执行一次
> `ALTER TABLE ledger_entries MODIFY COLUMN type ENUM('grant','preauth','confirm','refund') NOT NULL;`
> 全新 `docker compose up` 会自动应用新 DDL。
