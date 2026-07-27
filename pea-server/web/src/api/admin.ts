import { api } from './client';
import type { ModelType, PlanView, PricingRule } from './catalog';

/* ═══════════════════════════ 管理员类型 ═══════════════════════════ */

/** GET /admin/providers 单项 (密钥对外脱敏)。 */
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
  config: unknown;
}

export interface UpsertProviderInput {
  id?: string;
  name?: string;
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

export type RemoteModelType = 'image' | 'video' | 'text' | 'audio' | 'embedding';

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

/* ═══════════════════════════ 套餐 CRUD ═══════════════════════════ */

export const adminListPlans = () =>
  api.get<PlanView[]>('/admin/plans').then((r) => r.data ?? []);

export const adminUpsertPlan = (dto: UpsertPlanInput) =>
  api.post<PlanView>('/admin/plans', dto).then((r) => r.data);

export const adminDeletePlan = (id: string) =>
  api.delete<{ ok: true }>(`/admin/plans/${id}`).then((r) => r.data);
