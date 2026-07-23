import {
  Injectable,
  BadRequestException,
  NotFoundException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import { RedisPubSubService } from '../../infra/redis-pubsub.service';
import { EVENTS_CHANNEL } from '../../pea-events';

export interface BalanceResult {
  userId: number;
  balance: number;
  version: number;
}

/**
 * 积分双记账本 (ARCH D12 / ADR-006).
 *
 * 强一致保证（资深开发复核后修正，对应 T-ACC-03 验收）:
 *  - 并发安全: 余额变更走事务 + `accounts` 行级排他锁 (SELECT ... FOR UPDATE)。
 *    说明: 此处采用**悲观锁**而非 `version` 乐观锁——余额是热点单行,
 *    悲观锁在强一致扣费场景下比乐观锁(重试)更稳更简单, 且跨 BFF 实例也能由 MySQL 行锁串行化。
 *    `accounts.version` 仍单调递增, 仅作审计/变更序号, 不参与并发控制。
 *  - 幂等: 幂等校验**必须在获取行锁之后**执行 (见 preauthorize/refund)。
 *    原因: ledger_entries 唯一键为 (txn_id, created_at) — 分区表要求唯一索引含分区列,
 *    故 DB 层无法单独约束 txn_id 全局唯一, 必须由应用层在锁内二次校验,
 *    否则并发同 txn_id 会双扣/双退 (原实现把幂等检查放在 FOR UPDATE 之前的致命缺陷)。
 *  - 可追溯: 每笔余额变动都落借贷行; 注册时写 grant(贷方) 作为对账基准, 使
 *    balance == SUM(credit) - SUM(debit) 恒成立 (原有实现缺 grant 行, 无法对账)。
 */
@Injectable()
export class BillingService {
  constructor(
    private readonly db: DatabaseService,
    private readonly pubsub: RedisPubSubService,
  ) {}

  async getBalance(userId: number): Promise<BalanceResult> {
    const rows = await this.db.query<any[]>(
      'SELECT user_id, balance, version FROM accounts WHERE user_id = ?',
      [userId],
    );
    if (!rows.length) throw new NotFoundException('account not found');
    return { userId: rows[0].user_id, balance: rows[0].balance, version: rows[0].version };
  }

  async listLedger(userId: number, page = 1, size = 20) {
    const offset = (page - 1) * size;
    const rows = await this.db.query<any[]>(
      `SELECT id, txn_id, job_id, type, debit, credit, balance_after, created_at
       FROM ledger_entries WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?`,
      [userId, size, offset],
    );
    return rows;
  }

  /** 预扣: 立即扣减余额并记借方. 幂等 (同一 txn_id 重复调用不双扣). */
  async preauthorize(
    userId: number,
    amount: number,
    txnId: string,
    jobId?: string,
  ): Promise<BalanceResult> {
    if (amount <= 0) throw new BadRequestException('amount must be positive');

    const result = await this.db.transaction(async (conn) => {
      // 1) 先取行锁, 串行化同一账户的并发变更 (跨实例也由 MySQL 行锁保证)
      const [accRows] = await conn.query(
        'SELECT balance, version FROM accounts WHERE user_id = ? FOR UPDATE',
        [userId],
      );
      const acc = (accRows as any[])[0];
      if (!acc) throw new NotFoundException('account not found');

      // 2) 锁内二次校验幂等 (关键: 必须在 FOR UPDATE 之后, 否则并发同 txn_id 会双扣)
      const [existing] = await conn.query(
        'SELECT id FROM ledger_entries WHERE txn_id = ?',
        [txnId],
      );
      if ((existing as any[]).length) {
        return { balance: acc.balance, version: acc.version };
      }

      if (acc.balance < amount) {
        throw new BadRequestException('insufficient Tapies');
      }

      const balanceAfter = acc.balance - amount;
      await conn.query(
        `INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
         VALUES (?, ?, ?, ?, ?, 0, ?)`,
        [userId, txnId, jobId ?? null, 'preauth', amount, balanceAfter],
      );
      const [upd] = await conn.query(
        'UPDATE accounts SET balance = ?, version = version + 1 WHERE user_id = ?',
        [balanceAfter, userId],
      );
      // 行锁已保证串行, affectedRows 理论上恒为 1; 留作防御性断言
      if ((upd as any).affectedRows !== 1) {
        throw new BadRequestException('concurrent update conflict');
      }
      return { balance: balanceAfter, version: acc.version + 1 };
    });

    await this.pubsub.publish(EVENTS_CHANNEL, {
      kind: 'balance.changed',
      userId,
      balance: result.balance,
      delta: -amount,
      reason: 'preauth',
      ts: Date.now(),
    });
    return { userId, ...result };
  }

  /** 确认: 预扣已即时扣费, 确认不再改余额, 仅作幂等占位 (当前无调用方, 保留接口). */
  async confirm(userId: number, _amount: number, txnId: string, _jobId?: string) {
    return this.db.transaction(async (conn) => {
      const [existing] = await conn.query(
        'SELECT id FROM ledger_entries WHERE txn_id = ?',
        [txnId],
      );
      return { ok: true, duplicated: (existing as any[]).length > 0 };
    });
  }

  /** 退还: 失败补偿, 余额回加并记贷方. 幂等 (同一 txn_id 重复调用不双退). 由 orchestrator 经 /internal 调用. */
  async refund(userId: number, amount: number, txnId: string, jobId?: string) {
    const result = await this.db.transaction(async (conn) => {
      // 1) 先取行锁
      const [accRows] = await conn.query(
        'SELECT balance, version FROM accounts WHERE user_id = ? FOR UPDATE',
        [userId],
      );
      const acc = (accRows as any[])[0];
      if (!acc) throw new NotFoundException('account not found');

      // 2) 锁内二次校验幂等 (原实现同样错误地放在加锁之前)
      const [existing] = await conn.query(
        'SELECT id FROM ledger_entries WHERE txn_id = ?',
        [txnId],
      );
      if ((existing as any[]).length) return null; // 已退还

      const balanceAfter = acc.balance + amount;
      await conn.query(
        `INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
         VALUES (?, ?, ?, ?, 0, ?, ?)`,
        [userId, txnId, jobId ?? null, 'refund', amount, balanceAfter],
      );
      await conn.query(
        'UPDATE accounts SET balance = ?, version = version + 1 WHERE user_id = ?',
        [balanceAfter, userId],
      );
      return { balance: balanceAfter, version: acc.version + 1 };
    });

    if (result) {
      await this.pubsub.publish(EVENTS_CHANNEL, {
        kind: 'balance.changed',
        userId,
        balance: result.balance,
        delta: amount,
        reason: 'refund',
        ts: Date.now(),
      });
    }
    return { ok: true, refunded: !!result };
  }
}
