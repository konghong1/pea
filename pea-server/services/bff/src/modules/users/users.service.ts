import { Injectable, NotFoundException } from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';

export interface AuthzContext {
  id: number;
  email: string;
  role: 'user' | 'admin';
  planLevel: number;
  /** 生效权益等级: 套餐过期后回落为 0 (读取时判定, 无需定时任务)。 */
  effectivePlanLevel: number;
  planExpiresAt: string | null;
}

@Injectable()
export class UsersService {
  constructor(private readonly db: DatabaseService) {}

  /** 面向前端的资料 (含角色/权益/余额)。 */
  async getProfile(userId: number) {
    const rows = await this.db.query<any[]>(
      `SELECT u.id, u.email, u.display_name, u.avatar_url, u.role,
              u.plan_level, u.plan_expires_at, u.created_at,
              COALESCE(a.balance, 0) AS balance
       FROM users u LEFT JOIN accounts a ON a.user_id = u.id
       WHERE u.id = ?`,
      [userId],
    );
    if (!rows.length) throw new NotFoundException('user not found');
    const r = rows[0];
    const effective = this.effectivePlanLevel(r.plan_level, r.plan_expires_at);
    return {
      id: r.id,
      email: r.email,
      displayName: r.display_name,
      avatarUrl: r.avatar_url,
      role: r.role,
      planLevel: r.plan_level,
      effectivePlanLevel: effective,
      planExpiresAt: r.plan_expires_at,
      balance: r.balance,
      isAdmin: r.role === 'admin',
    };
  }

  /** 授权上下文: 供 Guard / 访问控制使用 (角色 + 生效权益等级)。 */
  async getAuthzContext(userId: number): Promise<AuthzContext> {
    const rows = await this.db.query<any[]>(
      'SELECT id, email, role, plan_level, plan_expires_at FROM users WHERE id = ?',
      [userId],
    );
    if (!rows.length) throw new NotFoundException('user not found');
    const r = rows[0];
    return {
      id: r.id,
      email: r.email,
      role: r.role,
      planLevel: r.plan_level,
      effectivePlanLevel: this.effectivePlanLevel(r.plan_level, r.plan_expires_at),
      planExpiresAt: r.plan_expires_at,
    };
  }

  async isAdmin(userId: number): Promise<boolean> {
    const rows = await this.db.query<any[]>(
      'SELECT role FROM users WHERE id = ?',
      [userId],
    );
    return rows.length > 0 && rows[0].role === 'admin';
  }

  /** 套餐过期即回落为 0 级。null 到期时间视为不过期 (如免费级)。 */
  private effectivePlanLevel(planLevel: number, expiresAt: string | Date | null): number {
    if (!planLevel || planLevel <= 0) return 0;
    if (expiresAt && new Date(expiresAt).getTime() < Date.now()) return 0;
    return planLevel;
  }
}
