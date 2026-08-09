import { api } from './client';
import type { ModelType, PlanView, PricingRule } from './catalog';

/* ═══════════════════════════ 管理员类型 ═══════════════════════════ */

/** GET /admin/providers 单项 (密钥对外脱敏)。 */
export interface ProviderView {
  id: string;
  name: string;
  /** 向后兼容保留: 始终与 protocol 同值。前端优先读 protocol/vendor。 */
  providerType: string;
  /** 协议族 (openai-compatible / anthropic-compatible / vendor-native)。 */
  protocol: string;
  /** 厂商 (minimax / agnes / openai / anthropic / 自定义); vendor-native 时必填。 */
  vendor: string;
  baseUrl: string;
  apiKeyMasked: string;
  hasApiKey: boolean;
  kind: 'image' | 'video' | 'text' | 'audio' | '3d';
  enabled: boolean;
  isDefault: boolean;
  config: unknown;
}

export interface UpsertProviderInput {
  id?: string;
  name?: string;
  /** 协议族 (优先字段)。 */
  protocol?: string;
  /** 厂商 (vendor-native 时必填)。 */
  vendor?: string;
  /** 向后兼容保留, 缺省时后端用 protocol 兜底。 */
  providerType?: string;
  baseUrl?: string;
  /** 传空/不传时后端保留原密钥 (避免编辑其他字段误清空)。 */
  apiKey?: string;
  kind?: ProviderView['kind'];
  enabled?: boolean;
  isDefault?: boolean;
  config?: unknown;
}

/** GET /admin/models 单项 (完整定价 / 门槛)。 */
export interface ModelView {
  id: string;
  providerId: string;
  modelName: string;
  displayName: string;
  modelType: ModelType;
  enabled: boolean;
  isDefault: boolean;
  minPlanLevel: number;
  pricing: PricingRule | null;
  paramsSchema: unknown;
  description: string;
  sortOrder: number;
}

export interface UpsertModelInput {
  id?: string;
  providerId?: string;
  modelName?: string;
  displayName?: string;
  modelType?: ModelType;
  enabled?: boolean;
  isDefault?: boolean;
  minPlanLevel?: number;
  pricing?: PricingRule | null;
  paramsSchema?: unknown;
  description?: string;
  sortOrder?: number;
}

export interface UpsertPlanInput {
  id: string;
  name?: string;
  planLevel?: number;
  priceCents?: number;
  tapies?: number;
  durationDays?: number;
  enabled?: boolean;
  sortOrder?: number;
  features?: string[];
}

export type RemoteModelType = 'image' | 'video' | 'text' | 'audio' | 'embedding' | '3d';

export interface RemoteModel {
  id: string;
  owned_by?: string;
  modelType?: RemoteModelType;
}

/* ═══════════════════════════ 提供商 CRUD ═══════════════════════════ */

export const adminListProviders = () =>
  api.get<ProviderView[]>('/admin/providers').then((r) => r.data ?? []);

export const adminCreateProvider = (dto: UpsertProviderInput) =>
  api.post<ProviderView>('/admin/providers', dto).then((r) => r.data);

export const adminUpdateProvider = (id: string, dto: UpsertProviderInput) =>
  api.patch<ProviderView>(`/admin/providers/${id}`, dto).then((r) => r.data);

export const adminDeleteProvider = (id: string) =>
  api.delete<{ ok: true }>(`/admin/providers/${id}`).then((r) => r.data);

/** 拉取提供商远端可用模型 (GET {base}/v1/models), 按类型持久化后返回。 */
export const adminFetchRemoteModels = (id: string) =>
  api
    .post<{ models: RemoteModel[] }>(`/admin/providers/${id}/fetch-models`)
    .then((r) => r.data.models ?? []);

/** 列出某提供商已持久化的远端模型 (按类型, 供下拉选择)。 */
export const adminListRemoteModels = (id: string) =>
  api
    .get<RemoteModel[]>(`/admin/providers/${id}/remote-models`)
    .then((r) => r.data ?? []);

/* ═══════════════════════════ 模型 CRUD ═══════════════════════════ */

export const adminListModels = (providerId?: string) =>
  api
    .get<ModelView[]>('/admin/models', { params: providerId ? { providerId } : undefined })
    .then((r) => r.data ?? []);

export const adminCreateModel = (dto: UpsertModelInput) =>
  api.post<ModelView>('/admin/models', dto).then((r) => r.data);

export const adminUpdateModel = (id: string, dto: UpsertModelInput) =>
  api.patch<ModelView>(`/admin/models/${id}`, dto).then((r) => r.data);

export const adminDeleteModel = (id: string) =>
  api.delete<{ ok: true }>(`/admin/models/${id}`).then((r) => r.data);

/** 定价试算明细单项 (后端 CostBreakdownItem 的镜像)。 */
export interface CostBreakdownItem {
  dim: string;
  value: string;
  delta: number;
  hit: boolean;
}

export interface CostPreview {
  cost: number;
  base: number;
  items: CostBreakdownItem[];
  subtotal: number;
  multiplierParam: string | null;
  multiplier: number;
  /** 后端清洗后的规则 —— 管理员能看到"实际会存成什么" */
  normalizedPricing: PricingRule | null;
  maxMultiplier: number;
}

/**
 * 草稿定价试算: 不需要模型已落库, 直接把编辑器当前规则发给后端算价。
 * 用的是与真实扣费同一段引擎, 所以配置界面看到的价 = 用户实际被扣的价。
 */
export const adminPreviewCost = (pricing: PricingRule | null, params: Record<string, unknown>) =>
  api
    .post<CostPreview>('/admin/models/preview-cost', { pricing, params })
    .then((r) => r.data);

/* ═══════════════════════════ 套餐 CRUD ═══════════════════════════ */

export const adminListPlans = () =>
  api.get<PlanView[]>('/admin/plans').then((r) => r.data ?? []);

export const adminUpsertPlan = (dto: UpsertPlanInput) =>
  api.post<PlanView>('/admin/plans', dto).then((r) => r.data);

export const adminDeletePlan = (id: string) =>
  api.delete<{ ok: true }>(`/admin/plans/${id}`).then((r) => r.data);

/* ═══════════════════════ 速率限制规则 CRUD ═══════════════════════ */

/**
 * 上游厂商配额的客户端建模 (编排器分布式令牌桶的数据源)。
 * 维度 (provider_id[, model_id][, tier])，编排器按
 * (厂商,模型,档位) > (厂商,模型) > (厂商,档位) > (厂商) 优先级匹配。
 * 字段用 snake_case —— 与 BFF DTO / DB 列一致，避免多一层映射出错。
 */
export interface RateLimitRule {
  id: number;
  provider_id: string;
  model_id: string | null;
  /** 图像档位 1K/2K/3K/4K；null = 该 provider/model 的任意档共享一个桶。 */
  tier: string | null;
  /** 每窗口允许的请求数。 */
  limit_n: number;
  /** 窗口秒数。Agnes 4K = 1 次 / 60s。 */
  window_s: number;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface UpsertRateLimitInput {
  provider_id?: string;
  model_id?: string | null;
  tier?: string | null;
  limit_n?: number;
  window_s?: number;
  enabled?: boolean;
}

export const adminListRateLimits = (filter?: { providerId?: string; modelId?: string }) =>
  api
    .get<RateLimitRule[]>('/admin/rate-limits', {
      params: filter?.providerId || filter?.modelId ? filter : undefined,
    })
    .then((r) => r.data ?? []);

export const adminCreateRateLimit = (dto: UpsertRateLimitInput) =>
  api.post<RateLimitRule>('/admin/rate-limits', dto).then((r) => r.data);

export const adminUpdateRateLimit = (id: number, dto: UpsertRateLimitInput) =>
  api.patch<RateLimitRule>(`/admin/rate-limits/${id}`, dto).then((r) => r.data);

export const adminDeleteRateLimit = (id: number) =>
  api.delete<{ ok: true }>(`/admin/rate-limits/${id}`).then((r) => r.data);
