import { Injectable, NotFoundException } from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';

export interface ProviderView {
  id: string;
  name: string;
  kind: 'image' | 'video' | 'text' | 'audio';
  enabled: boolean;
  isDefault: boolean;
  config: any;
}

/** 默认 Provider 种子 (FR-G7)：首次访问按用户复制一份, 支持按用户独立开关/默认。 */
const DEFAULT_PROVIDERS: { id: string; name: string; kind: ProviderView['kind'] }[] = [
  { id: 'mock-image', name: 'Mock 图像生成', kind: 'image' },
  { id: 'mock-video', name: 'Mock 视频生成', kind: 'video' },
  { id: 'flux', name: 'FLUX.1 图像', kind: 'image' },
  { id: 'seedance', name: 'Seedance 2.0', kind: 'video' },
  { id: 'openai-gpt', name: 'OpenAI GPT', kind: 'text' },
];

/**
 * AI Provider 配置 (T-G-06 / FR-G7):
 *  - 列表: 首次访问从默认种子复制为本用户配置 (按用户隔离, 持久化).
 *  - 开关 enabled / 设为默认 is_default (同用户唯一默认).
 */
@Injectable()
export class ProvidersService {
  constructor(private readonly db: DatabaseService) {}

  async list(userId: number): Promise<ProviderView[]> {
    const existing = await this.db.query<any[]>(
      'SELECT id FROM ai_providers WHERE owner_id = ?',
      [userId],
    );
    if (!existing.length) {
      for (const p of DEFAULT_PROVIDERS) {
        await this.db.query(
          `INSERT INTO ai_providers (id, owner_id, name, kind, enabled, is_default, config_json)
           VALUES (?, ?, ?, ?, 1, ?, NULL)`,
          [p.id, userId, p.name, p.kind, p.id === 'mock-image' ? 1 : 0],
        );
      }
    }
    const rows = await this.db.query<any[]>(
      `SELECT id, name, kind, enabled, is_default, config_json
       FROM ai_providers WHERE owner_id = ? ORDER BY kind, id`,
      [userId],
    );
    return rows.map(normalize);
  }

  async update(
    userId: number,
    id: string,
    dto: { enabled?: boolean; isDefault?: boolean },
  ): Promise<{ ok: true }> {
    const found = await this.db.query<any[]>(
      'SELECT id FROM ai_providers WHERE owner_id = ? AND id = ?',
      [userId, id],
    );
    if (!found.length) throw new NotFoundException('provider not found');

    return this.db.transaction(async (conn) => {
      if (typeof dto.enabled === 'boolean') {
        await conn.query(
          'UPDATE ai_providers SET enabled = ? WHERE owner_id = ? AND id = ?',
          [dto.enabled ? 1 : 0, userId, id],
        );
      }
      if (dto.isDefault === true) {
        await conn.query('UPDATE ai_providers SET is_default = 0 WHERE owner_id = ?', [userId]);
        await conn.query(
          'UPDATE ai_providers SET is_default = 1 WHERE owner_id = ? AND id = ?',
          [userId, id],
        );
      }
      return { ok: true } as const;
    });
  }
}

function normalize(r: any): ProviderView {
  return {
    id: r.id,
    name: r.name,
    kind: r.kind,
    enabled: !!r.enabled,
    isDefault: !!r.is_default,
    config: r.config_json,
  };
}
