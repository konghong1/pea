import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import { CreateRateLimitDto, UpdateRateLimitDto } from './rate-limits.dto';

export interface RateLimitRule {
  id: number;
  provider_id: string;
  model_id: string | null;
  tier: string | null;
  limit_n: number;
  window_s: number;
  enabled: boolean;
  created_at: any;
  updated_at: any;
}

/**
 * 速率限制规则后台配置 (编排器侧分布式令牌桶的数据源)。
 *
 * 规则维度: (provider_id[, model_id][, tier])。编排器加载时按
 * (provider,model,tier) > (provider,model) > (provider,tier) > (provider) 优先级匹配,
 * 命中规则的 scope 决定共享桶, 保证"同厂商级规则下所有模型共享一个桶"。
 * 改完无需重启编排器: 编排器以 provider_rate_limit_ttl_s(默认 30s) 缓存重载。
 */
@Injectable()
export class RateLimitsService {
  constructor(private readonly db: DatabaseService) {}

  async list(filter?: { providerId?: string; modelId?: string }): Promise<RateLimitRule[]> {
    const where: string[] = [];
    const params: any[] = [];
    if (filter?.providerId) {
      where.push('provider_id = ?');
      params.push(filter.providerId);
    }
    if (filter?.modelId) {
      where.push('model_id = ?');
      params.push(filter.modelId);
    }
    const sql =
      `SELECT id, provider_id, model_id, tier, limit_n, window_s, enabled, created_at, updated_at
       FROM provider_rate_limits
       ${where.length ? 'WHERE ' + where.join(' AND ') : ''}
       ORDER BY provider_id, model_id, tier`;
    const rows = await this.db.query<any[]>(sql, params);
    return rows.map((r) => this.toRule(r));
  }

  async create(dto: CreateRateLimitDto): Promise<RateLimitRule> {
    if (!dto.provider_id) throw new BadRequestException('provider_id required');
    if (!Number.isInteger(dto.limit_n) || dto.limit_n < 1) {
      throw new BadRequestException('limit_n must be integer >= 1');
    }
    if (!Number.isInteger(dto.window_s) || dto.window_s < 1) {
      throw new BadRequestException('window_s must be integer >= 1');
    }
    const tier = dto.tier ? dto.tier.toUpperCase() : null;
    const modelId = dto.model_id || null;
    const enabled = dto.enabled === false ? 0 : 1;
    await this.db.query(
      `INSERT INTO provider_rate_limits (provider_id, model_id, tier, limit_n, window_s, enabled)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [dto.provider_id, modelId, tier, dto.limit_n, dto.window_s, enabled],
    );
    const rows = await this.db.query<any[]>(
      'SELECT * FROM provider_rate_limits WHERE provider_id = ? ORDER BY id DESC LIMIT 1',
      [dto.provider_id],
    );
    return this.toRule(rows[0]);
  }

  async update(id: string, dto: UpdateRateLimitDto): Promise<RateLimitRule> {
    await this.getRaw(id); // 404 if missing
    const sets: string[] = [];
    const vals: any[] = [];
    if (dto.provider_id !== undefined) {
      sets.push('provider_id = ?');
      vals.push(dto.provider_id);
    }
    if (dto.model_id !== undefined) {
      sets.push('model_id = ?');
      vals.push(dto.model_id || null);
    }
    if (dto.tier !== undefined) {
      sets.push('tier = ?');
      vals.push(dto.tier ? dto.tier.toUpperCase() : null);
    }
    if (dto.limit_n !== undefined) {
      if (!Number.isInteger(dto.limit_n) || dto.limit_n < 1) {
        throw new BadRequestException('limit_n must be integer >= 1');
      }
      sets.push('limit_n = ?');
      vals.push(dto.limit_n);
    }
    if (dto.window_s !== undefined) {
      if (!Number.isInteger(dto.window_s) || dto.window_s < 1) {
        throw new BadRequestException('window_s must be integer >= 1');
      }
      sets.push('window_s = ?');
      vals.push(dto.window_s);
    }
    if (dto.enabled !== undefined) {
      sets.push('enabled = ?');
      vals.push(dto.enabled ? 1 : 0);
    }
    if (sets.length) {
      vals.push(id);
      await this.db.query(
        `UPDATE provider_rate_limits SET ${sets.join(', ')} WHERE id = ?`,
        vals,
      );
    }
    return this.getView(id);
  }

  async remove(id: string): Promise<{ ok: true }> {
    const res: any = await this.db.query(
      'DELETE FROM provider_rate_limits WHERE id = ?',
      [id],
    );
    if (res.affectedRows === 0) throw new NotFoundException('rate-limit rule not found');
    return { ok: true };
  }

  private async getRaw(id: string): Promise<any> {
    const rows = await this.db.query<any[]>(
      'SELECT * FROM provider_rate_limits WHERE id = ?',
      [id],
    );
    if (!rows.length) throw new NotFoundException('rate-limit rule not found');
    return rows[0];
  }

  private async getView(id: string): Promise<RateLimitRule> {
    return this.toRule(await this.getRaw(id));
  }

  private toRule(r: any): RateLimitRule {
    return { ...r, enabled: !!r.enabled };
  }
}
