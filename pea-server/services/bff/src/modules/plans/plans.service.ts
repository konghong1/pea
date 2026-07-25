import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import { RedisPubSubService } from '../../infra/redis-pubsub.service';
import { EVENTS_CHANNEL } from '../../pea-events';

export interface PlanView {
  id: string;
  name: string;
  planLevel: number;
  priceCents: number;
  tapies: number;
  durationDays: number;
  enabled: boolean;
  sortOrder: number;
  features: string[];
}

/**
 * 套餐售卖 + 购买。购买是"到账 Tapies + 赋予 plan_level + 有效期"的原子事务:
 *  - accounts 行级锁 (FOR UPDATE) 串行化同账户并发, 与 BillingService 一致。
 *  - 锁内幂等 (txn_id 二次校验), 防重复点击/重试双到账。
 *  - grant 流水 + user_plans 记录 + users 权益更新, 全部同事务提交。
 * 说明: 当前无真实支付网关, 购买即视为已支付并立即发放 (符合"买套餐即有 Tapies")。
 */
@Injectable()
export class PlansService {
  constructor(
    private readonly db: DatabaseService,
    private readonly pubsub: RedisPubSubService,
  ) {}

  async listPlans(includeDisabled = false): Promise<PlanView[]> {
    const rows = includeDisabled
      ? await this.db.query<any[]>('SELECT * FROM billing_plans ORDER BY sort_order, plan_level')
      : await this.db.query<any[]>('SELECT * FROM billing_plans WHERE enabled = 1 ORDER BY sort_order, plan_level');
    return rows.map(toView);
  }

  async purchase(userId: number, planId: string, idempotencyKey?: string) {
    const txnId = idempotencyKey
      ? `purchase:${idempotencyKey}`
      : `purchase:${userId}:${planId}:${Date.now()}:${Math.random().toString(36).slice(2)}`;

    const result = await this.db.transaction(async (conn) => {
      const [planRows] = await conn.query(
        'SELECT * FROM billing_plans WHERE id = ? AND enabled = 1',
        [planId],
      );
      const plan = (planRows as any[])[0];
      if (!plan) throw new NotFoundException('plan not found');
      if (plan.price_cents <= 0) {
        // 免费/0 元套餐不可购买 (防止刷 Tapies); 免费权益在注册时已发放。
        throw new BadRequestException('该套餐不可购买');
      }

      // 行锁: 串行化同账户并发变更
      const [accRows] = await conn.query(
        'SELECT balance, version FROM accounts WHERE user_id = ? FOR UPDATE',
        [userId],
      );
      const acc = (accRows as any[])[0];
      if (!acc) throw new NotFoundException('account not found');

      // 锁内幂等
      const [existing] = await conn.query(
        'SELECT id FROM ledger_entries WHERE txn_id = ?',
        [txnId],
      );
      if ((existing as any[]).length) {
        return { balance: acc.balance, duplicated: true, plan, expiresAt: null as Date | null };
      }

      const balanceAfter = acc.balance + plan.tapies;
      await conn.query(
        `INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
         VALUES (?, ?, NULL, 'grant', 0, ?, ?)`,
        [userId, txnId, plan.tapies, balanceAfter],
      );
      await conn.query(
        'UPDATE accounts SET balance = ?, version = version + 1 WHERE user_id = ?',
        [balanceAfter, userId],
      );

      const expiresAt =
        plan.duration_days > 0
          ? new Date(Date.now() + plan.duration_days * 86400000)
          : null;
      await conn.query(
        `INSERT INTO user_plans (user_id, plan_id, plan_level, tapies_granted, price_cents, expires_at)
         VALUES (?, ?, ?, ?, ?, ?)`,
        [userId, planId, plan.plan_level, plan.tapies, plan.price_cents, expiresAt],
      );
      await conn.query(
        'UPDATE users SET plan_level = ?, plan_expires_at = ? WHERE id = ?',
        [plan.plan_level, expiresAt, userId],
      );

      return { balance: balanceAfter, duplicated: false, plan, expiresAt };
    });

    if (!result.duplicated) {
      await this.pubsub.publish(EVENTS_CHANNEL, {
        kind: 'balance.changed',
        userId,
        balance: result.balance,
        delta: result.plan.tapies,
        reason: 'grant',
        ts: Date.now(),
      });
    }

    return {
      ok: true,
      duplicated: result.duplicated,
      balance: result.balance,
      planId,
      planLevel: result.plan.plan_level,
      tapiesGranted: result.duplicated ? 0 : result.plan.tapies,
      expiresAt: result.expiresAt,
    };
  }

  // ── Admin CRUD ────────────────────────────────────────────────
  async upsertPlan(input: any): Promise<PlanView> {
    const id = (input.id ?? '').trim();
    if (!id) throw new BadRequestException('plan id required');
    await this.db.query(
      `INSERT INTO billing_plans
         (id, name, plan_level, price_cents, tapies, duration_days, enabled, sort_order, features_json)
       VALUES (?,?,?,?,?,?,?,?,?)
       ON DUPLICATE KEY UPDATE
         name=VALUES(name), plan_level=VALUES(plan_level), price_cents=VALUES(price_cents),
         tapies=VALUES(tapies), duration_days=VALUES(duration_days), enabled=VALUES(enabled),
         sort_order=VALUES(sort_order), features_json=VALUES(features_json)`,
      [
        id, input.name ?? id, input.planLevel ?? 1, input.priceCents ?? 0,
        input.tapies ?? 0, input.durationDays ?? 30,
        input.enabled === false ? 0 : 1, input.sortOrder ?? 0,
        input.features != null ? JSON.stringify(input.features) : null,
      ],
    );
    const rows = await this.db.query<any[]>('SELECT * FROM billing_plans WHERE id = ?', [id]);
    return toView(rows[0]);
  }

  async deletePlan(id: string): Promise<{ ok: true }> {
    const res: any = await this.db.query('DELETE FROM billing_plans WHERE id = ?', [id]);
    if (res.affectedRows === 0) throw new NotFoundException('plan not found');
    return { ok: true };
  }
}

function toView(r: any): PlanView {
  let features: string[] = [];
  const raw = r.features_json;
  if (raw) {
    try {
      features = typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch {
      features = [];
    }
  }
  return {
    id: r.id,
    name: r.name,
    planLevel: r.plan_level,
    priceCents: r.price_cents,
    tapies: r.tapies,
    durationDays: r.duration_days,
    enabled: !!r.enabled,
    sortOrder: r.sort_order,
    features,
  };
}
