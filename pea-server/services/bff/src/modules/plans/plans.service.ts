import {
  Injectable,
  NotFoundException,
  BadRequestException,
  ForbiddenException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
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
 * 权益发放快照。订单在「下单那一刻」把套餐参数固化下来，
 * 之后套餐改价 / 下架 / 改等级都不影响历史订单的履约。
 */
export interface EntitlementSnapshot {
  planId: string;
  planLevel: number;
  tapies: number;
  durationDays: number;
  priceCents: number;
}

/**
 * 套餐售卖 + 购买。购买是"到账 Tapies + 赋予 plan_level + 有效期"的原子事务:
 *  - accounts 行级锁 (FOR UPDATE) 串行化同账户并发, 与 BillingService 一致。
 *  - 锁内幂等 (txn_id 二次校验), 防重复点击/重试双到账。
 *  - grant 流水 + user_plans 记录 + users 权益更新, 全部同事务提交。
 *
 * ⚠️ 支付边界 (2026-08 修复):
 *   grantPlan() 是"无条件发放"的底层动作, 调用方必须自行确保钱已收到。
 *   - 用户自助 purchase(): 默认禁用 (PEA_ALLOW_SELF_PURCHASE=0)。此前无任何支付校验,
 *     任意登录用户可无限 POST /plans/purchase 白嫖 Tapies 并自提 plan_level。
 *   - 正规路径: 下单 -> 扫收款码付款 -> 管理员核对到账 -> 调 grantPlan() 发放。
 */
@Injectable()
export class PlansService {
  constructor(
    private readonly db: DatabaseService,
    private readonly pubsub: RedisPubSubService,
    private readonly config: ConfigService,
  ) {}

  async listPlans(includeDisabled = false): Promise<PlanView[]> {
    const rows = includeDisabled
      ? await this.db.query<any[]>('SELECT * FROM billing_plans ORDER BY sort_order, plan_level')
      : await this.db.query<any[]>('SELECT * FROM billing_plans WHERE enabled = 1 ORDER BY sort_order, plan_level');
    return rows.map(toView);
  }

  /**
   * 用户自助购买入口。
   * ⚠️ 无支付校验 —— 默认由 PEA_ALLOW_SELF_PURCHASE 关闭, 仅供无外部用户的内网演示环境临时开启。
   */
  async purchase(userId: number, planId: string, idempotencyKey?: string) {
    if (!this.config.get<boolean>('allowSelfPurchase')) {
      throw new ForbiddenException(
        '自助开通已关闭。请在套餐页下单并扫码付款，到账后由管理员为你开通对应权益。',
      );
    }
    const txnId = idempotencyKey
      ? `purchase:${idempotencyKey}`
      : `purchase:${userId}:${planId}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
    return this.grantPlan(userId, planId, txnId);
  }

  /**
   * 无条件发放套餐权益（按套餐当前配置）。等价于 grantEntitlement + 现查快照。
   *
   * ⚠️ 本方法不做任何支付校验，调用方必须已确认款项到账。
   */
  async grantPlan(userId: number, planId: string, txnId: string) {
    const rows = await this.db.query<any[]>(
      'SELECT * FROM billing_plans WHERE id = ? AND enabled = 1',
      [planId],
    );
    const plan = rows[0];
    if (!plan) throw new NotFoundException('plan not found');
    if (plan.price_cents <= 0) {
      // 免费/0 元套餐不可购买 (防止刷 Tapies); 免费权益在注册时已发放。
      throw new BadRequestException('该套餐不可购买');
    }
    return this.grantEntitlement(
      userId,
      {
        planId,
        planLevel: plan.plan_level,
        tapies: plan.tapies,
        durationDays: plan.duration_days,
        priceCents: plan.price_cents,
      },
      txnId,
    );
  }

  /**
   * 按快照发放权益（Tapies 到账 + plan_level + 有效期），全程单事务 + txnId 幂等。
   *
   * 权益等级/有效期的合并规则（避免"买低档把高档踩下去"）：
   *   - 新等级 >  当前有效等级 → 升级，有效期从现在起重算
   *   - 新等级 == 当前有效等级 → 续期，在原到期时间上叠加（未过期则接续，已过期则从现在起）
   *   - 新等级 <  当前有效等级 → 只到账 Tapies，不降级、不改到期时间
   *
   * ⚠️ 不做支付校验，调用方必须已确认款项到账：
   *    - 订单审核通过（txnId = `order:{orderNo}`，保证一单只发一次）
   *    - 支付网关回调（txnId = `order:{orderNo}`，与人工路径共用同一幂等键）
   */
  async grantEntitlement(userId: number, snap: EntitlementSnapshot, txnId: string) {
    const result = await this.db.transaction(async (conn) => {
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
        return { balance: acc.balance, duplicated: true, expiresAt: null as Date | null };
      }

      const balanceAfter = acc.balance + snap.tapies;
      await conn.query(
        `INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
         VALUES (?, ?, NULL, 'grant', 0, ?, ?)`,
        [userId, txnId, snap.tapies, balanceAfter],
      );
      await conn.query(
        'UPDATE accounts SET balance = ?, version = version + 1 WHERE user_id = ?',
        [balanceAfter, userId],
      );

      // 读当前权益状态，按合并规则算新的 plan_level / plan_expires_at
      const [userRows] = await conn.query(
        'SELECT plan_level, plan_expires_at FROM users WHERE id = ? FOR UPDATE',
        [userId],
      );
      const cur = (userRows as any[])[0] ?? { plan_level: 0, plan_expires_at: null };
      const now = Date.now();
      const curExpiresMs = cur.plan_expires_at ? new Date(cur.plan_expires_at).getTime() : null;
      // 当前等级是否仍在有效期内 (expires 为 null 视为永久有效)
      const curActive = cur.plan_level > 0 && (curExpiresMs === null || curExpiresMs > now);
      const curLevel = curActive ? cur.plan_level : 0;
      const durMs = snap.durationDays > 0 ? snap.durationDays * 86400000 : 0;

      let nextLevel = curLevel;
      let nextExpires: Date | null = curActive && curExpiresMs ? new Date(curExpiresMs) : null;

      if (snap.planLevel > curLevel) {
        // 升级: 有效期从现在起重算
        nextLevel = snap.planLevel;
        nextExpires = durMs > 0 ? new Date(now + durMs) : null;
      } else if (snap.planLevel === curLevel && snap.planLevel > 0) {
        // 续期: 未过期则接续叠加, 已过期则从现在起
        if (durMs > 0) {
          const base = curExpiresMs && curExpiresMs > now ? curExpiresMs : now;
          nextExpires = new Date(base + durMs);
        } else {
          nextExpires = null; // 买到永久档
        }
      }
      // snap.planLevel < curLevel: 不降级、不动到期时间, 仅 Tapies 到账

      await conn.query(
        `INSERT INTO user_plans (user_id, plan_id, plan_level, tapies_granted, price_cents, expires_at)
         VALUES (?, ?, ?, ?, ?, ?)`,
        [userId, snap.planId, snap.planLevel, snap.tapies, snap.priceCents, nextExpires],
      );
      await conn.query(
        'UPDATE users SET plan_level = ?, plan_expires_at = ? WHERE id = ?',
        [nextLevel, nextExpires, userId],
      );

      return { balance: balanceAfter, duplicated: false, expiresAt: nextExpires, nextLevel };
    });

    if (!result.duplicated) {
      await this.pubsub.publish(EVENTS_CHANNEL, {
        kind: 'balance.changed',
        userId,
        balance: result.balance,
        delta: snap.tapies,
        reason: 'grant',
        ts: Date.now(),
      });
    }

    return {
      ok: true,
      duplicated: result.duplicated,
      balance: result.balance,
      planId: snap.planId,
      planLevel: (result as any).nextLevel ?? snap.planLevel,
      tapiesGranted: result.duplicated ? 0 : snap.tapies,
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
