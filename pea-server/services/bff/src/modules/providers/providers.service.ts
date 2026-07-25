import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import axios from 'axios';
import { DatabaseService } from '../../database/database.service';

export interface ProviderView {
  id: string;
  name: string;
  providerType: string;
  baseUrl: string;
  apiKeyMasked: string;
  hasApiKey: boolean;
  kind: 'image' | 'video' | 'text' | 'audio';
  enabled: boolean;
  isDefault: boolean;
  config: any;
}

export interface UpsertProviderInput {
  id?: string;
  name: string;
  providerType?: string;
  baseUrl?: string;
  apiKey?: string;
  kind?: ProviderView['kind'];
  enabled?: boolean;
  isDefault?: boolean;
  config?: any;
}

/**
 * AI 提供商 (全局, 仅管理员可写)。密钥明文存内网库, 对外一律脱敏。
 */
@Injectable()
export class ProvidersService {
  constructor(private readonly db: DatabaseService) {}

  async listProviders(): Promise<ProviderView[]> {
    const rows = await this.db.query<any[]>(
      `SELECT id, name, provider_type, base_url, api_key, kind, enabled, is_default, config_json
       FROM ai_providers ORDER BY is_default DESC, id`,
    );
    return rows.map(toView);
  }

  /** 内部使用: 返回含明文密钥的原始行 (禁止经控制器直接返回)。 */
  async getRaw(id: string): Promise<any> {
    const rows = await this.db.query<any[]>(
      'SELECT * FROM ai_providers WHERE id = ?',
      [id],
    );
    if (!rows.length) throw new NotFoundException('provider not found');
    return rows[0];
  }

  async createProvider(input: UpsertProviderInput): Promise<ProviderView> {
    const id = (input.id ?? '').trim();
    if (!id) throw new BadRequestException('provider id required');
    if (!/^[a-z0-9][a-z0-9_-]{1,63}$/i.test(id)) {
      throw new BadRequestException('invalid provider id (a-z0-9_- only)');
    }
    const dup = await this.db.query<any[]>('SELECT id FROM ai_providers WHERE id = ?', [id]);
    if (dup.length) throw new BadRequestException('provider id already exists');

    await this.db.transaction(async (conn) => {
      if (input.isDefault) {
        await conn.query('UPDATE ai_providers SET is_default = 0');
      }
      await conn.query(
        `INSERT INTO ai_providers
           (id, name, provider_type, base_url, api_key, kind, enabled, is_default, config_json)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          id,
          input.name ?? id,
          input.providerType ?? 'openai-compatible',
          input.baseUrl ?? '',
          input.apiKey ?? '',
          input.kind ?? 'image',
          input.enabled === false ? 0 : 1,
          input.isDefault ? 1 : 0,
          input.config != null ? JSON.stringify(input.config) : null,
        ],
      );
    });
    return this.getView(id);
  }

  async updateProvider(id: string, input: Partial<UpsertProviderInput>): Promise<ProviderView> {
    await this.getRaw(id); // 404 if missing
    await this.db.transaction(async (conn) => {
      const sets: string[] = [];
      const vals: any[] = [];
      if (input.name !== undefined) { sets.push('name = ?'); vals.push(input.name); }
      if (input.providerType !== undefined) { sets.push('provider_type = ?'); vals.push(input.providerType); }
      if (input.baseUrl !== undefined) { sets.push('base_url = ?'); vals.push(input.baseUrl); }
      // 空/未传 api_key 时保留原值, 避免管理员编辑其他字段时误清空密钥。
      if (input.apiKey !== undefined && input.apiKey !== '') { sets.push('api_key = ?'); vals.push(input.apiKey); }
      if (input.kind !== undefined) { sets.push('kind = ?'); vals.push(input.kind); }
      if (input.enabled !== undefined) { sets.push('enabled = ?'); vals.push(input.enabled ? 1 : 0); }
      if (input.config !== undefined) { sets.push('config_json = ?'); vals.push(input.config != null ? JSON.stringify(input.config) : null); }
      if (sets.length) {
        vals.push(id);
        await conn.query(`UPDATE ai_providers SET ${sets.join(', ')} WHERE id = ?`, vals);
      }
      if (input.isDefault === true) {
        await conn.query('UPDATE ai_providers SET is_default = 0');
        await conn.query('UPDATE ai_providers SET is_default = 1 WHERE id = ?', [id]);
      }
    });
    return this.getView(id);
  }

  async deleteProvider(id: string): Promise<{ ok: true }> {
    const res: any = await this.db.query(
      'DELETE FROM ai_providers WHERE id = ?',
      [id],
    );
    if (res.affectedRows === 0) throw new NotFoundException('provider not found');
    return { ok: true };
  }

  /**
   * 拉取远端可用模型列表 (GET {base_url}/v1/models)。仅返回列表, 不落库;
   * 由管理员从中挑选后调 models CRUD 添加。
   */
  async fetchRemoteModels(id: string): Promise<{ models: { id: string; owned_by?: string }[] }> {
    const p = await this.getRaw(id);
    if (!p.base_url) throw new BadRequestException('provider has no base_url');
    const url = normalizeModelsUrl(p.base_url);
    try {
      const { data } = await axios.get(url, {
        headers: p.api_key ? { Authorization: `Bearer ${p.api_key}` } : {},
        timeout: 20000,
      });
      const list = Array.isArray(data?.data) ? data.data : [];
      return {
        models: list
          .filter((m: any) => m && m.id)
          .map((m: any) => ({ id: String(m.id), owned_by: m.owned_by })),
      };
    } catch (e: any) {
      const detail = e?.response?.data
        ? JSON.stringify(e.response.data).slice(0, 300)
        : e?.message ?? 'unknown';
      throw new BadRequestException(`fetch remote models failed: ${detail}`);
    }
  }

  private async getView(id: string): Promise<ProviderView> {
    const rows = await this.db.query<any[]>(
      `SELECT id, name, provider_type, base_url, api_key, kind, enabled, is_default, config_json
       FROM ai_providers WHERE id = ?`,
      [id],
    );
    return toView(rows[0]);
  }
}

function maskKey(key: string | null): string {
  if (!key) return '';
  if (key.length <= 12) return '****';
  return `${key.slice(0, 6)}****${key.slice(-4)}`;
}

function toView(r: any): ProviderView {
  return {
    id: r.id,
    name: r.name,
    providerType: r.provider_type,
    baseUrl: r.base_url,
    apiKeyMasked: maskKey(r.api_key),
    hasApiKey: !!r.api_key,
    kind: r.kind,
    enabled: !!r.enabled,
    isDefault: !!r.is_default,
    config: r.config_json,
  };
}

/** base_url 归一化到 {host}/v1/models (无论是否已带 /v1)。 */
function normalizeModelsUrl(baseUrl: string): string {
  let base = baseUrl.replace(/\/+$/, '');
  if (base.endsWith('/v1')) base = base.slice(0, -3);
  return `${base}/v1/models`;
}
