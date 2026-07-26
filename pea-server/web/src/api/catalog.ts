import { api } from './client';

/* ═══════════════════════════ 用户侧类型 ═══════════════════════════ */

export type ModelType = 'image' | 'video' | 'text';

/** GET /users/me 返回结构 (camelCase, 与 BFF UsersService.getProfile 对齐)。 */
export interface MeProfile {
  id: number;
  email: string;
  displayName: string;
  avatarUrl: string | null;
  role: 'user' | 'admin';
  planLevel: number;
  /** 生效权益等级: 套餐过期回落 0。用于前端模型解锁展示。 */
  effectivePlanLevel: number;
  planExpiresAt: string | null;
  balance: number;
  isAdmin: boolean;
}

/** 动态定价规则 (与 BFF PricingService.PricingRule 对齐)。 */
export interface PricingRule {
  base?: number;
  /** { size: { '2K': 5, '4K': 20 }, duration: { '10': 40 } } */
  tiers?: Record<string, Record<string, number>>;
  /** 数量倍率参数名 (最终价 = (base + Σdelta) * clamp(req[multiplier])) */
  multiplier?: string;
}

/** GET /models/available 单项 (含是否解锁 + 基础参考价)。 */
export interface AvailableModel {
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
  /** 当前用户是否可调用 (effectivePlanLevel >= minPlanLevel)。 */
  allowed: boolean;
  /** 基础参考价 (pricing.base)。精确价随参数由 estimateCost 计。 */
  baseCost: number;
}

/** POST /models/estimate 返回。 */
export interface EstimateResult {
  modelId: string;
  cost: number;
  allowed: boolean;
  minPlanLevel: number;
  effectivePlanLevel: number;
}

/** GET /plans 单项。 */
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

export interface PurchaseResult {
  ok: boolean;
  duplicated: boolean;
  balance: number;
  planId: string;
  planLevel: number;
  tapiesGranted: number;
  expiresAt: string | null;
}

export interface AcceptJobResult {
  jobId: string;
  status: string;
  costTapies: number;
  model: { id: string; name: string; modelName: string };
}

/* ═══════════════════════════ 用户侧 API ═══════════════════════════ */

export async function getMe(): Promise<MeProfile> {
  const { data } = await api.get<MeProfile>('/users/me');
  return data;
}

/** 列出所有启用模型 (标注是否解锁 + 基础参考价), 可按类型过滤。 */
export async function listAvailableModels(type?: ModelType): Promise<AvailableModel[]> {
  const { data } = await api.get<AvailableModel[]>('/models/available', {
    params: type ? { type } : undefined,
  });
  return data ?? [];
}

/** 价格预估 (按参数动态计价)。 */
export async function estimateCost(
  modelId: string,
  params: Record<string, unknown> = {},
): Promise<EstimateResult> {
  const { data } = await api.post<EstimateResult>('/models/estimate', { modelId, params });
  return data;
}

export async function listPlans(): Promise<PlanView[]> {
  const { data } = await api.get<PlanView[]>('/plans');
  return data ?? [];
}

/** 购买套餐。idempotencyKey 防重复到账 (同键多次提交只发放一次)。 */
export async function purchasePlan(
  planId: string,
  idempotencyKey?: string,
): Promise<PurchaseResult> {
  const { data } = await api.post<PurchaseResult>('/plans/purchase', { planId, idempotencyKey });
  return data;
}

export interface AcceptJobInput {
  type: ModelType;
  prompt: string;
  model?: string;
  params?: Record<string, unknown>;
  priority?: 'normal' | 'fast';
  idempotencyKey?: string;
  /** 图片/视频节点所选平台配置 id (提示词构造层据此拼平台化提示词) */
  platformConfigId?: string | null;
}

/** 受理一次生成 (服务端按 模型+参数 权威算价并预扣, 客户端不得指定金额)。电商套图等批量生成走此接口; 节点图片/视频请改用 acceptNodeGenerationJob。 */
export async function acceptGenerationJob(input: AcceptJobInput): Promise<AcceptJobResult> {
  const { data } = await api.post<AcceptJobResult>('/generation/jobs', input);
  return data;
}

/* ════════════════════ 平台提示词配置 (Phase2) ═══════════════════════════ */

/** 节点图片/视频生成专用输入 (不含 platformConfigId: 节点自身用「比例/分辨率」UI 拼参, 不带平台配置)。 */
export interface AcceptNodeJobInput {
  type: ModelType;
  prompt: string;
  model?: string;
  params?: Record<string, unknown>;
  priority?: 'normal' | 'fast';
  idempotencyKey?: string;
}

/** 节点图片/视频生成 — 独立接口 POST /generation/node, 与电商套图 /generation/jobs 解耦。 */
export async function acceptNodeGenerationJob(input: AcceptNodeJobInput): Promise<AcceptJobResult> {
  const { data } = await api.post<AcceptJobResult>('/generation/node', input);
  return data;
}

/* ═══════════════════════════ token 用量 (Phase3) ═══════════════════════════ */

export interface UsageSummaryRow {
  node_type: 'text' | 'image' | 'video';
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  calls: number;
}

/** 当前用户 token 用量汇总。 */
export async function listUsageSummary(): Promise<UsageSummaryRow[]> {
  const { data } = await api.get<UsageSummaryRow[]>('/usage/summary');
  return data ?? [];
}
