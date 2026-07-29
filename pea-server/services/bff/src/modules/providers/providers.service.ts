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

/** 远端模型能力类型 (比 ai_models.model_type 更宽, 覆盖提供商实际返回的各类模型)。 */
export type RemoteModelType = 'image' | 'video' | 'text' | 'audio' | 'embedding';

export interface RemoteModelEntry {
  id: string;
  owned_by?: string;
  modelType: RemoteModelType;
}

/**
 * 从模型 id / provider 元数据推断能力类型 (参考 ai-agent 的 _suggest_model_type)。
 * 优先级: provider 返回的结构化类型/能力 → model id 关键字启发式 (image→video→embedding→audio→text 兜底)。
 */
const IMAGE_HINTS = [
  'dall-e', 'dalle', 'image', 'imagen', 'stable-diffusion', 'sdxl', 'flux', 'cogview',
  'niji', 'illustrious', 'pony', 'draw', 'paint', 'cartoon', 'art', 'vision',
  'gpt-image', 'gemini', 'midjourney', 'wanx', 'tongyi', 'doubao', 'jiimagine',
];
const VIDEO_HINTS = [
  'sora', 'video', 'kling', 'cogvideo', 'runway', 'pika', 'luma', 'veo', 'wan',
  'seedance', 'digo', 'hunyuan-video', 'doubao-video', 'kami', 'mochi',
];
const EMBEDDING_HINTS = [
  'embedding', 'bge', 'text-embedding', 'e5-', 'gte-', 'm3e', 'bce',
  'jina-embed', 'voyage', 'cohere-embed', 'embed',
];
const AUDIO_HINTS = [
  'tts', 'whisper', 'speech', 'audio', 'voice', 'music', 'suno', 'udio',
  'cosyvoice', 'chattts', 'bark', 'fishaudio',
];

export function suggestModelType(modelId: string, raw?: any): RemoteModelType {
  const lower = (modelId || '').toLowerCase();
  if (raw && typeof raw === 'object') {
    const explicit = raw.type || raw.category || raw.model_type || raw.task;
    if (typeof explicit === 'string') {
      const e = explicit.toLowerCase();
      if (/(image|img|draw|paint)/.test(e)) return 'image';
      if (/(video|movie|film)/.test(e)) return 'video';
      if (/(embed)/.test(e)) return 'embedding';
      if (/(audio|speech|tts|voice|music|sound)/.test(e)) return 'audio';
      if (/(text|chat|llm|language)/.test(e)) return 'text';
    }
    const caps =
      raw.capabilities || raw.modality || raw.modalities ||
      raw.input_modalities || raw.output_modalities || raw.architecture?.modality;
    const capStr = Array.isArray(caps) ? caps.join(',') : caps ? String(caps) : '';
    if (capStr) {
      const c = capStr.toLowerCase();
      if (/(image|img)/.test(c)) return 'image';
      if (/(video|movie|film)/.test(c)) return 'video';
      if (/(embed)/.test(c)) return 'embedding';
      if (/(audio|speech|voice|music|sound)/.test(c)) return 'audio';
    }
  }
  if (IMAGE_HINTS.some((k) => lower.includes(k))) return 'image';
  if (VIDEO_HINTS.some((k) => lower.includes(k))) return 'video';
  if (EMBEDDING_HINTS.some((k) => lower.includes(k))) return 'embedding';
  if (AUDIO_HINTS.some((k) => lower.includes(k))) return 'audio';
  return 'text';
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
   * 拉取远端可用模型列表 (GET {base_url}/v1/models), 推断类型并**按类型持久化**到
   * provider_remote_models (幂等 upsert), 返回带 modelType 的列表, 供模型配置下拉选择。
   */
  async fetchRemoteModels(id: string): Promise<{ models: RemoteModelEntry[] }> {
    const p = await this.getRaw(id);
    if (!p.base_url) throw new BadRequestException('provider has no base_url');
    // AI 网关兜底: 仅在显式配置 PEA_AI_GATEWAY 时启用。
    // ★ 默认必须为空 —— 之前默认 host.docker.internal:33210 是开发机专属代理,
    //   服务器上无此代理, 兜底反而把真实的主地址错误掩盖成
    //   "connect ECONNREFUSED 172.17.0.1:33210", 极难排查。
    const gateway = (process.env.PEA_AI_GATEWAY || '').trim().replace(/\/+$/, '');
    const errDetail = (e: any): string =>
      e?.response?.data
        ? JSON.stringify(e.response.data).slice(0, 300)
        : e?.message ?? 'unknown';
    const tryFetch = async (baseUrl: string): Promise<any[]> => {
      const url = normalizeModelsUrl(baseUrl);
      const { data } = await axios.get(url, {
        headers: p.api_key ? { Authorization: `Bearer ${p.api_key}` } : {},
        timeout: 20000,
      });
      return Array.isArray(data?.data) ? data.data : [];
    };
    let list: any[] = [];
    const primary = p.base_url.replace(/\/+$/, '');
    const useGateway = !!gateway && gateway !== primary;
    try {
      list = await tryFetch(p.base_url);
    } catch (e: any) {
      const primaryErr = errDetail(e);
      if (!useGateway) {
        throw new BadRequestException(
          `fetch remote models failed: ${primaryErr} (url=${normalizeModelsUrl(p.base_url)})`,
        );
      }
      try {
        console.warn(`[providers] official base_url unreachable (${primaryErr}), fallback to gateway ${gateway}`);
        list = await tryFetch(gateway);
      } catch (e2: any) {
        // 两路都失败: 必须同时报出主地址与网关的错误, 不能只报网关错误掩盖根因。
        throw new BadRequestException(
          `fetch remote models failed: primary(${normalizeModelsUrl(p.base_url)}): ${primaryErr}; ` +
          `gateway(${gateway}): ${errDetail(e2)}`,
        );
      }
    }
    const models: RemoteModelEntry[] = list
      .filter((m: any) => m && m.id)
      .map((m: any) => {
        const mid = String(m.id);
        return { id: mid, owned_by: m.owned_by, modelType: suggestModelType(mid, m) };
      });
    // 落库: 按类型持久化 (provider_id + remote_model_id 唯一, 重复拉取只更新类型/归属)
    if (models.length) {
      const rows = models.map((m) => [p.id, m.id, m.owned_by ?? null, m.modelType]);
      await this.db.query(
        `INSERT INTO provider_remote_models (provider_id, remote_model_id, owned_by, model_type)
         VALUES ?
         ON DUPLICATE KEY UPDATE owned_by = VALUES(owned_by), model_type = VALUES(model_type), updated_at = NOW(3)`,
        [rows],
      );
    }
    return { models };
  }

  /** 列出某提供商已持久化的远端模型 (按类型分组, 供下拉选择)。 */
  async listRemoteModels(id: string): Promise<RemoteModelEntry[]> {
    await this.getRaw(id); // 404 if missing
    const rows = await this.db.query<any[]>(
      `SELECT remote_model_id AS id, owned_by AS owned_by, model_type AS modelType
       FROM provider_remote_models WHERE provider_id = ?
       ORDER BY model_type, remote_model_id`,
      [id],
    );
    return rows.map((r) => ({
      id: r.id,
      owned_by: r.owned_by ?? undefined,
      modelType: r.modelType,
    }));
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
