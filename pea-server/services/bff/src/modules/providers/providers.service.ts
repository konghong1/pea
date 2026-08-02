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
  // MiniMax 视频族: H 系列(v2) / 海螺(v1) / 定向生成系列。
  // 'minimax-h' 只命中 H3 等视频模型, 不会误伤文本的 MiniMax-M2。
  'minimax-h', 'hailuo', 't2v-', 'i2v-', 's2v-',
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
    // Anthropic 的 /v1/models 每项都带 type:"model" —— 这是对象种类标记而非能力类型,
    // 不排除掉会让后续的类型推断误以为拿到了权威信息。
    if (typeof explicit === 'string' && explicit.toLowerCase() === 'model') {
      // 无信息量, 落到下方 id 关键字启发式
    } else if (typeof explicit === 'string') {
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
 * MiniMax 静态模型目录。
 *
 * ⚠️ 为什么必须硬编码: MiniMax 的 `GET /v1/models` **只返回文本模型**
 * (实测 2026-08 返回 MiniMax-M3/M2.7/M2.5/M2.1/M2 共 8 个)。视频、图像、音乐、
 * 语音模型分散在 /v2/video_generation、/v1/image_generation、/v1/music_generation、
 * /v1/t2a_v2 等专用端点上, 官方**没有**统一的能力发现接口。
 * 只依赖 /v1/models 的话, 管理员在"模型 & 定价"里永远选不到视频模型。
 *
 * 远端拉到的同名条目优先级更高 (以上游为准), 这里只做补齐。
 */
const MINIMAX_STATIC_MODELS: RemoteModelEntry[] = [
  // 视频 v2 (多模态 content 数组端点)
  { id: 'MiniMax-H3', owned_by: 'minimax', modelType: 'video' },
  // 视频 v1 (扁平 body + file_id 两段取回)
  { id: 'MiniMax-Hailuo-02', owned_by: 'minimax', modelType: 'video' },
  { id: 'T2V-01-Director', owned_by: 'minimax', modelType: 'video' },
  { id: 'I2V-01-Director', owned_by: 'minimax', modelType: 'video' },
  { id: 'S2V-01', owned_by: 'minimax', modelType: 'video' },
  { id: 'video-01', owned_by: 'minimax', modelType: 'video' },
  // 图像 (同步出图)
  { id: 'image-01', owned_by: 'minimax', modelType: 'image' },
  { id: 'image-01-live', owned_by: 'minimax', modelType: 'image' },
  // 音乐 / 语音 (适配器已支持; 平台侧音频节点就绪后即可上架)
  { id: 'music-1.5', owned_by: 'minimax', modelType: 'audio' },
  { id: 'speech-2.5-hd-preview', owned_by: 'minimax', modelType: 'audio' },
  { id: 'speech-2.5-turbo-preview', owned_by: 'minimax', modelType: 'audio' },
  { id: 'speech-02-hd', owned_by: 'minimax', modelType: 'audio' },
  { id: 'speech-02-turbo', owned_by: 'minimax', modelType: 'audio' },
];

/** 该提供商是否需要静态目录补齐 (按 provider_type + base_url 双重判定)。 */
function staticCatalogFor(providerType: string, baseUrl: string): RemoteModelEntry[] {
  const t = (providerType || '').toLowerCase();
  const u = (baseUrl || '').toLowerCase();
  // anthropic 兼容层只暴露文本模型, 其 /v1/models 已够用, 无需补齐。
  if (t === 'minimax' || (t !== 'anthropic-compatible' && u.includes('minimax'))) {
    return MINIMAX_STATIC_MODELS;
  }
  return [];
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
    // Anthropic Messages 协议的模型端点认证方式与 OpenAI 不同: 需要 x-api-key +
    // anthropic-version。两个头都发是安全的 —— MiniMax 兼容层与官方都接受。
    const isAnthropic = String(p.provider_type || '').toLowerCase() === 'anthropic-compatible';
    const authHeaders = (): Record<string, string> => {
      if (!p.api_key) return {};
      const h: Record<string, string> = { Authorization: `Bearer ${p.api_key}` };
      if (isAnthropic) {
        h['x-api-key'] = p.api_key;
        h['anthropic-version'] = '2023-06-01';
      }
      return h;
    };
    const tryFetch = async (baseUrl: string): Promise<any[]> => {
      const url = normalizeModelsUrl(baseUrl);
      const { data } = await axios.get(url, {
        // 🔑 与 ai-agent 的 httpx(trust_env=False) 等价: 强制不走 HTTPS_PROXY 环境变量,
        // 直接出网。否则容器里的 HTTPS_PROXY=host.docker.internal:33210(开发机专属死代理)
        // 会劫持本请求, 在服务器上表现为 read ECONNRESET / ECONNREFUSED。
        proxy: false,
        headers: authHeaders(),
        timeout: 20000,
      });
      return Array.isArray(data?.data) ? data.data : [];
    };
    const staticCatalog = staticCatalogFor(p.provider_type, p.base_url);
    let list: any[] = [];
    const primary = p.base_url.replace(/\/+$/, '');
    const useGateway = !!gateway && gateway !== primary;
    try {
      list = await tryFetch(p.base_url);
    } catch (e: any) {
      const primaryErr = errDetail(e);
      let gatewayErr: string | null = null;
      if (useGateway) {
        try {
          console.warn(`[providers] official base_url unreachable (${primaryErr}), fallback to gateway ${gateway}`);
          list = await tryFetch(gateway);
        } catch (e2: any) {
          gatewayErr = errDetail(e2);
        }
      }
      if (!useGateway || gatewayErr) {
        // 有静态目录的提供商 (MiniMax): 探测失败不致命 —— 视频/图像模型本来就不在
        // /v1/models 里, 静态目录足以让管理员完成配置。降级而非报错。
        if (staticCatalog.length) {
          console.warn(
            `[providers] ${p.id}: /v1/models probe failed (${primaryErr}), ` +
            `serving ${staticCatalog.length} static catalog entries only`,
          );
        } else {
          const detail = gatewayErr
            ? `primary(${normalizeModelsUrl(p.base_url)}): ${primaryErr}; gateway(${gateway}): ${gatewayErr}`
            : `${primaryErr} (url=${normalizeModelsUrl(p.base_url)})`;
          throw new BadRequestException(`fetch remote models failed: ${detail}`);
        }
      }
    }
    const models: RemoteModelEntry[] = list
      .filter((m: any) => m && m.id)
      .map((m: any) => {
        const mid = String(m.id);
        return { id: mid, owned_by: m.owned_by, modelType: suggestModelType(mid, m) };
      });
    // 静态目录补齐: 远端已返回的同名条目以远端为准 (大小写不敏感去重)。
    if (staticCatalog.length) {
      const seen = new Set(models.map((m) => m.id.toLowerCase()));
      for (const s of staticCatalog) {
        if (!seen.has(s.id.toLowerCase())) {
          models.push(s);
          seen.add(s.id.toLowerCase());
        }
      }
    }
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
