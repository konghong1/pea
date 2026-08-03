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
  protocol: string;
  vendor: string;
  baseUrl: string;
  apiKeyMasked: string;
  hasApiKey: boolean;
  kind: 'image' | 'video' | 'text' | 'audio' | '3d';
  enabled: boolean;
  isDefault: boolean;
  config: any;
}

export interface UpsertProviderInput {
  id?: string;
  name: string;
  providerType?: string;
  protocol?: string;
  vendor?: string;
  baseUrl?: string;
  apiKey?: string;
  kind?: ProviderView['kind'];
  enabled?: boolean;
  isDefault?: boolean;
  config?: any;
}

/** 远端模型能力类型 (比 ai_models.model_type 更宽, 覆盖提供商实际返回的各类模型)。 */
export type RemoteModelType = 'image' | 'video' | 'text' | 'audio' | 'embedding' | '3d';

export interface RemoteModelEntry {
  id: string;
  owned_by?: string;
  modelType: RemoteModelType;
}

/**
 * 从模型 id / provider 元数据推断能力类型 (参考 ai-agent 的 _suggest_model_type)。
 * 优先级: provider 返回的结构化类型/能力 → model id 关键字启发式 (image→video→embedding→audio→text 兜底)。
 */
/**
 * 关键字表的铁律: **只放能力级词, 绝不放厂商/系列名**。
 *
 * 反面教材 (已修): 曾把裸 'doubao' 放进 IMAGE_HINTS。但 doubao 是火山方舟的
 * 全谱系品牌 —— 文本(doubao-pro)、图像(doubao-seedream)、视频(doubao-seedance)、
 * 向量(doubao-embedding)、3D(doubao-seed3d) 全都叫 doubao-*。一个裸厂商名命中,
 * 127 个模型里 99 个被判成 image。同类地雷还有 'gemini' / 'tongyi'。
 *
 * 另一类地雷是**过短的泛词**: 'art' 会命中 doubao-sm[art]-router;
 * 裸 'wan' 会命中图像模型 wanx。子串匹配没有词边界概念, 宁可写长不可写短。
 *
 * 'vision' 也已移除 —— VLM(视觉语言模型) 是"图进文出"的对话模型, 不是文生图。
 */
const IMAGE_HINTS = [
  'dall-e', 'dalle', 'image', 'imagen', 'stable-diffusion', 'sdxl', 'flux', 'cogview',
  'niji', 'illustrious', 'pony', 'draw', 'paint', 'cartoon',
  'gpt-image', 'midjourney', 'wanx', 'jiimagine',
  // 火山方舟图像族: Seedream(文生图) / SeedEdit(图生图编辑)
  'seedream', 'seededit',
  // Google 图像族: nano-banana 是 gemini-*-image 的品牌别名 (models/nano-banana-pro-preview),
  // 该 id 里不含 'image', 不单独列就会掉进 text 兜底。
  // 'imagen' 已在上方; 裸 'gemini' 绝不能加 (它是 Google 全谱系品牌名)。
  'nano-banana',
];
const VIDEO_HINTS = [
  'sora', 'video', 'kling', 'cogvideo', 'runway', 'pika', 'luma', 'veo',
  'digo', 'hunyuan-video', 'doubao-video', 'kami', 'mochi',
  // 火山方舟视频族: Seedance / Seaweed
  'seedance', 'seaweed',
  // 通义万相视频 (wan2-1-14b-t2v / i2v / flf2v)。
  // 必须带版本号: 裸 'wan' 会误伤图像模型 wanx。
  'wan2-', 'wan2.',
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
  // Google 音乐生成族 (lyria-3-clip-preview / lyria-3-pro-preview), 走 generateContent,
  // 权威字段区分不出来, 只能靠 id。
  'lyria',
];
// 3D 生成族 (火山方舟 3DGeneration / Seed3D / Hyper3D / HiMeta3D)。用具体前缀, 绝不放裸 '3d' 以免误伤。
const _3D_HINTS = ['seed3d', 'hyper3d', 'hitem3d'];

export function suggestModelType(modelId: string, raw?: any): RemoteModelType {
  const lower = (modelId || '').toLowerCase();
  if (raw && typeof raw === 'object') {
    // Google Gemini 的权威能力声明是 supportedGenerationMethods (方法名数组)。
    // 只有三个方法能唯一确定能力, 其余必须放行到关键字启发式:
    //   predict            -> Imagen 文生图
    //   predictLongRunning -> Veo 视频
    //   embedContent       -> 向量
    // ⚠️ generateContent **不能**判成 text —— Gemini 的图像(gemini-3-pro-image)、
    //    TTS(gemini-2.5-flash-preview-tts)、音乐(lyria-*) 全都走 generateContent,
    //    一刀切会把整个图像族误判成文本 (与当年 doubao 全线误判为 image 同类错误)。
    const methods = raw.supportedGenerationMethods || raw.supported_generation_methods;
    if (Array.isArray(methods)) {
      const set = methods.map((x: any) => String(x));
      if (set.includes('predictLongRunning')) return 'video';
      if (set.includes('predict')) return 'image';
      if (set.includes('embedContent')) return 'embedding';
      // generateContent / countTokens / generateAnswer -> 落到下方 id 关键字启发式
    }
    // raw.domain 是火山方舟 /api/v3/models 的权威能力声明:
    //   LLM / VLM / ImageGeneration / VideoGeneration / Embedding / 3DGeneration / Router
    // 实测 127 个模型里 96 个带该字段。漏读它会让这批模型白白降级到关键字猜测 ——
    // 这正是 doubao-* 全线被误判为 image 的直接诱因。新接厂商时务必检查其
    // /models 响应里是否还有别的权威字段名, 有就加进这个列表。
    const explicit = raw.type || raw.category || raw.model_type || raw.task || raw.domain;
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
      if (/(3d|threed)/.test(e)) return '3d';
      // vlm = 视觉语言模型 (图进文出), 归 text —— 'llm' 匹配不到 'vlm', 必须显式列出。
      if (/(text|chat|llm|vlm|language)/.test(e)) return 'text';
      // 未覆盖的权威值 (如火山 Router) 继续往下走关键字启发式, 最终由 text 兜底。
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
      if (/(3d|threed)/.test(c)) return '3d';
    }
  }
  if (IMAGE_HINTS.some((k) => lower.includes(k))) return 'image';
  if (VIDEO_HINTS.some((k) => lower.includes(k))) return 'video';
  if (EMBEDDING_HINTS.some((k) => lower.includes(k))) return 'embedding';
  if (AUDIO_HINTS.some((k) => lower.includes(k))) return 'audio';
  if (_3D_HINTS.some((k) => lower.includes(k))) return '3d';
  return 'text';
}

/**
 * 协议族枚举: 与编排器 PROVIDER_REGISTRY 的 protocol 维度一致。
 * - openai-compatible    OpenAI Chat Completions 兼容协议
 * - anthropic-compatible Anthropic Messages 协议
 * - vendor-native        厂商自有协议 (如 MiniMax 原生 v2/v1), 需配合 vendor 字段路由；该厂商必须在编排器实现原生适配器，否则调用报错
 *
 * 注意: 旧代码的 "minimax" 这类厂商名**不属于**协议族, 一并归到 vendor-native + vendor=minimax。
 */
export const PROTOCOL_FAMILIES = [
  'openai-compatible',
  'anthropic-compatible',
  'vendor-native',
] as const;

/**
 * 已知厂商白名单 (仅作前端下拉提示, 不强制; 留空表示自定义厂商)。
 * 与编排器 @register_provider(protocol, vendor) 的 vendor 维度对应。
 */
export const KNOWN_VENDORS = ['minimax', 'agnes', 'volcengine', 'gemini', 'openai', 'anthropic'] as const;

/** 该 provider 是否为 Google Gemini (原生 Generative Language API)。
 *
 * 判定优先 vendor 字段, base_url 域名兜底 —— 前者应对自定义中转域名,
 * 后者应对历史数据里 vendor 未填的行。 */
function isGeminiProvider(vendor?: string, baseUrl?: string): boolean {
  if ((vendor || '').toLowerCase() === 'gemini') return true;
  return /generativelanguage\.googleapis\.com/i.test(baseUrl || '');
}

function toView(r: any): ProviderView {
  return {
    id: r.id,
    name: r.name,
    providerType: r.provider_type,
    protocol: r.protocol || r.provider_type || 'openai-compatible',
    vendor: r.vendor || '',
    baseUrl: r.base_url,
    apiKeyMasked: maskKey(r.api_key),
    hasApiKey: !!r.api_key,
    kind: r.kind,
    enabled: !!r.enabled,
    isDefault: !!r.is_default,
    config: r.config_json,
  };
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

/**
 * 火山方舟静态模型目录 (与 MiniMax 同理: 部分能力不在统一 /api/v3/models 列表里, 需补齐)。
 *  - 3D: doubao-seed3d-2-0-260328 / hyper3d-gen2-260112 / hitem3d-2-0-251223。
 *        实际上这三个也在 /api/v3/models 里 (domain=3DGeneration), suggestModelType 现已能识别并归类为 '3d';
 *        此处静态补齐仅作兜底 (防止个别账号 domain 字段缺失时降级成 text)。
 *  - 音乐: doubao-music —— 走独立 IAM 网关(imagination), 不在 /api/v3/models 中, 必须静态补齐。
 *        编排器侧为占位分支, 待开通服务并提供 IAM AK/SK 后接入 (见 volcengine.py)。
 */
const VOLCENGINE_STATIC_MODELS: RemoteModelEntry[] = [
  { id: 'doubao-seed3d-2-0-260328', owned_by: 'volcengine', modelType: '3d' },
  { id: 'hyper3d-gen2-260112', owned_by: 'volcengine', modelType: '3d' },
  { id: 'hitem3d-2-0-251223', owned_by: 'volcengine', modelType: '3d' },
  { id: 'doubao-music', owned_by: 'volcengine', modelType: 'audio' },
];

/** 该提供商是否需要静态目录补齐 (按 protocol + vendor + base_url 三重判定, 方案 A)。 */
function staticCatalogFor(protocol: string, vendor: string, baseUrl: string): RemoteModelEntry[] {
  const t = (protocol || '').toLowerCase();
  const v = (vendor || '').toLowerCase();
  const u = (baseUrl || '').toLowerCase();
  // 厂商原生协议 + MiniMax 厂商 -> 静态目录补齐 (视频/图像/音频分散在各专用端点)。
  if ((t === 'vendor-native' && v === 'minimax') || t === 'minimax') {
    return MINIMAX_STATIC_MODELS;
  }
  // 宽松兜底: base_url 命中 minimax 域名但 protocol 未标 vendor-native (旧/手配)。
  // anthropic 兼容层只暴露文本模型, 其 /v1/models 已够用, 无需补齐。
  if (t !== 'anthropic-compatible' && u.includes('minimax')) {
    return MINIMAX_STATIC_MODELS;
  }
  // 火山方舟: /api/v3/models 不含音乐 (且 3D 需靠 suggestModelType 兜底), 静态补齐。
  if ((t === 'vendor-native' && v === 'volcengine') || t === 'volcengine' || u.includes('volcengine')) {
    return VOLCENGINE_STATIC_MODELS;
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
      `SELECT id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default, config_json
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

    // 方案 A: protocol 为主维度, 默认 openai-compatible; provider_type 同步写入保持兼容。
    const protocol = (input.protocol ?? input.providerType ?? 'openai-compatible').trim();
    if (!PROTOCOL_FAMILIES.includes(protocol as any)) {
      throw new BadRequestException(`unknown protocol '${protocol}' (expected one of ${PROTOCOL_FAMILIES.join(', ')})`);
    }
    const vendor = (input.vendor ?? '').trim();
    // vendor-native 必须有厂商; 其它协议厂商可为空 (兼容层厂商由 base_url 推断)。
    if (protocol === 'vendor-native' && !vendor) {
      throw new BadRequestException("protocol='vendor-native' requires a vendor (e.g. minimax)");
    }
    const providerType = protocol; // 向后兼容: provider_type 与 protocol 同值

    await this.db.transaction(async (conn) => {
      if (input.isDefault) {
        await conn.query('UPDATE ai_providers SET is_default = 0');
      }
      await conn.query(
        `INSERT INTO ai_providers
           (id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default, config_json)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          id,
          input.name ?? id,
          providerType,
          vendor,
          protocol,
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

    // 协议/厂商变更时做同样的守门校验 (与 createProvider 一致)。
    const current = await this.getRaw(id);
    const nextProtocol = (input.protocol ?? input.providerType ?? current.provider_type ?? 'openai-compatible').trim();
    if (!PROTOCOL_FAMILIES.includes(nextProtocol as any)) {
      throw new BadRequestException(`unknown protocol '${nextProtocol}' (expected one of ${PROTOCOL_FAMILIES.join(', ')})`);
    }
    const nextVendor = (input.vendor !== undefined ? input.vendor : current.vendor ?? '').trim();
    if (nextProtocol === 'vendor-native' && !nextVendor) {
      throw new BadRequestException("protocol='vendor-native' requires a vendor (e.g. minimax)");
    }

    await this.db.transaction(async (conn) => {
      const sets: string[] = [];
      const vals: any[] = [];
      if (input.name !== undefined) { sets.push('name = ?'); vals.push(input.name); }
      if (input.protocol !== undefined || input.providerType !== undefined) {
        sets.push('provider_type = ?'); vals.push(nextProtocol);
        sets.push('protocol = ?'); vals.push(nextProtocol);
      }
      if (input.vendor !== undefined) { sets.push('vendor = ?'); vals.push(nextVendor); }
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
    // 把 axios 异常转成可读详情: 优先带 HTTP 状态码 + 针对性提示, 即使响应体为空也能看懂。
    const errDetail = (e: any): string => {
      const status = e?.response?.status;
      if (status) {
        const hint =
          status === 401 || status === 403
            ? ' (检查 provider 的 api_key 是否有效/有权限)'
            : status >= 500
              ? ' (上游服务异常, 稍后重试)'
              : '';
        const body = e.response.data;
        const bodyStr = body
          ? (typeof body === 'string' ? body : JSON.stringify(body)).slice(0, 200)
          : '';
        return `HTTP ${status}${bodyStr ? `: ${bodyStr}` : ''}${hint}`;
      }
      // 连接层失败 (无 HTTP 响应): DNS/TLS/超时等, 透传原始 message
      return e?.message ?? 'unknown (无响应)';
    };
    // Anthropic Messages 协议的模型端点认证方式与 OpenAI 不同: 需要 x-api-key +
    // anthropic-version。两个头都发是安全的 —— MiniMax 兼容层与官方都接受。
    // 判定改用 protocol 字段 (方案 A: 协议与厂商解耦)。
    const isAnthropic = String(p.protocol || p.provider_type || '').toLowerCase() === 'anthropic-compatible';
    const isGemini = isGeminiProvider(p.vendor, p.base_url);
    const authHeaders = (): Record<string, string> => {
      if (!p.api_key) return {};
      // ⚠️ Gemini 只认 x-goog-api-key, 且**多带一个 Authorization: Bearer 会直接 401**
      //   ("Expected OAuth 2 access token..." —— Google 认为你在用 OAuth 却给了个 API key)。
      //   所以这里必须 return, 不能像 Anthropic 那样叠加。已实测。
      if (isGemini) return { 'x-goog-api-key': p.api_key };
      const h: Record<string, string> = { Authorization: `Bearer ${p.api_key}` };
      if (isAnthropic) {
        h['x-api-key'] = p.api_key;
        h['anthropic-version'] = '2023-06-01';
      }
      return h;
    };
    const tryFetch = async (baseUrl: string): Promise<any[]> => {
      const url = normalizeModelsUrl(baseUrl, p.vendor);
      const { data } = await axios.get(url, {
        // 🔑 与 ai-agent 的 httpx(trust_env=False) 等价: 强制不走 HTTPS_PROXY 环境变量,
        // 直接出网。否则容器里的 HTTPS_PROXY=host.docker.internal:33210(开发机专属死代理)
        // 会劫持本请求, 在服务器上表现为 read ECONNRESET / ECONNREFUSED。
        proxy: false,
        headers: authHeaders(),
        timeout: 20000,
      });
      // OpenAI/Anthropic 系是 {data:[...]}; Google 原生是 {models:[...]}。
      // 两种形态都收, 避免为一家厂商再分叉一条抓取链路。
      if (Array.isArray(data?.data)) return data.data;
      if (Array.isArray(data?.models)) return data.models;
      return [];
    };
    const staticCatalog = staticCatalogFor(p.protocol || p.provider_type, p.vendor, p.base_url);
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
      // Google 原生 /models 用 `name` 作标识 (如 "models/gemini-2.5-flash"), 没有 `id`;
      // OpenAI/Anthropic 系用 `id`。两者都收, 否则 Gemini 模型会被整批过滤掉。
      .filter((m: any) => m && (m.id || m.name))
      .map((m: any) => {
        const mid = String(m.id || m.name);
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
      `SELECT id, name, provider_type, vendor, protocol, base_url, api_key, kind, enabled, is_default, config_json
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

/**
 * base_url 归一化到模型列表端点。
 * - Gemini 原生 Generative Language API: 走 /v1beta/models (非 OpenAI 的 /v1/models),
 *   且必须带 pageSize (实测 58 个模型一次拉全, 无 nextPageToken 分页)。
 *   容忍 base 带或不带 /v1beta 两种写法。
 * - Volcengine 方舟 base 以 /api/v3 结尾 -> {base}/models (其 OpenAI 兼容前缀是 /api/v3, 非 /v1)。
 * - 其它 (Agnes 的 /v1, MiniMax 裸域名) 维持原行为: 剥 /v1 后拼 /v1/models。
 */
function normalizeModelsUrl(baseUrl: string, vendor?: string): string {
  let base = baseUrl.replace(/\/+$/, '');
  const isGemini =
    (vendor || '').toLowerCase() === 'gemini' ||
    /generativelanguage\.googleapis\.com/i.test(base);
  if (isGemini) {
    // 官方模型发现端点: GET /v1beta/models?pageSize=1000。
    // 注意: 多带 /v1beta 时用正则保底, 避免拼成 /v1beta/v1beta/models。
    if (!/v1beta\/?$/i.test(base)) base = `${base}/v1beta`;
    return `${base}/models?pageSize=1000`;
  }
  if (base.endsWith('/api/v3')) return `${base}/models`;
  if (base.endsWith('/v1')) base = base.slice(0, -3);
  return `${base}/v1/models`;
}
