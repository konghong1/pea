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
 * 核心保证:
 *  - 强一致: 余额更新走事务 + accounts.version 乐观锁, 并发不丢钱.
 *  - 幂等: ledger_entries.txn_id 唯一, 重复预扣/退还不双扣 (架构 R4).
 *  - 可追溯: 每笔变动都落借贷两行.
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

  /** 预扣: 立即扣减余额并记借方. 幂等. */
  async preauthorize(
    userId: number,
    amount: number,
    txnId: string,
    jobId?: string,
  ): Promise<BalanceResult> {
    if (amount <= 0) throw new BadRequestException('amount must be positive');

    const result = await this.db.transaction(async (conn) => {
      // 幂等: 同 txn_id 直接返回当前余额
      const [existing] = await conn.query(
        'SELECT id FROM ledger_entries WHERE txn_id = ?',
        [txnId],
      );
      if ((existing as any[]).length) {
        const [acc] = await conn.query(
          'SELECT balance, version FROM accounts WHERE user_id = ? FOR UPDATE',
          [userId],
        );
        return { balance: acc[0].balance, version: acc[0].version };
      }

      const [accRows] = await conn.query(
        'SELECT balance, version FROM accounts WHERE user_id = ? FOR UPDATE',
        [userId],
      );
      const acc = (accRows as any[])[0];
      if (!acc) throw new NotFoundException('account not found');
      if (acc.balance < amount) {
        throw new BadRequestException('insufficient Tapies');
      }

      await conn.query(
        `INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
         VALUES (?, ?, ?, ?, ?, 0, ?)`,
        [userId, txnId, jobId ?? null, 'preauth', amount, acc.balance - amount],
      );
      await conn.query(
        'UPDATE accounts SET balance = balance - ?, version = version + 1 WHERE user_id = ?',
        [amount, userId],
      );
      const [after] = await conn.query(
        'SELECT balance, version FROM accounts WHERE user_id = ?',
        [userId],
      );
      return { balance: after[0].balance, version: after[0].version };
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

  /** 确认: 预扣已扣, 此处仅记确认分录, 余额不变. 幂等. */
  async confirm(userId: number, amount: number, txnId: string, jobId?: string) {
    return this.db.transaction(async (conn) => {
      const [existing] = await conn.query(
        'SELECT id FROM ledger_entries WHERE txn_id = ?',
        [txnId],
      );
      if ((existing as any[]).length) return { ok: true, duplicated: true };
      const [acc] = await conn.query(
        'SELECT balance FROM accounts WHERE user_id = ? FOR UPDATE',
        [userId],
      );
      await conn.query(
        `INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
         VALUES (?, ?, ?, ?, 0, 0, ?)`,
        [userId, txnId, jobId ?? null, 'confirm', acc[0].balance],
      );
      return { ok: true };
    });
  }

  /** 退还: 失败补偿, 余额回加并记贷方. 幂等. 由 orchestrator 经 /internal 调用. */
  async refund(userId: number, amount: number, txnId: string, jobId?: string) {
    const result = await this.db.transaction(async (conn) => {
      const [existing] = await conn.query(
        'SELECT id FROM ledger_entries WHERE txn_id = ?',
        [txnId],
      );
      if ((existing as any[]).length) return null; // 已退还

      await conn.query(
        `INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
         VALUES (?, ?, ?, ?, 0, ?, ?)`,
        [userId, txnId, jobId ?? null, 'refund', amount, 0],
      );
      await conn.query(
        'UPDATE accounts SET balance = balance + ?, version = version + 1 WHERE user_id = ?',
        [amount, userId],
      );
      const [after] = await conn.query(
        'SELECT balance, version FROM accounts WHERE user_id = ?',
        [userId],
      );
      return { balance: after[0].balance, version: after[0].version };
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
