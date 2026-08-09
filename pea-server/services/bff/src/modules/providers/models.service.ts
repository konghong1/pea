import {
  Injectable,
  NotFoundException,
  BadRequestException,
  ForbiddenException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import { UsersService } from '../users/users.service';
import { MAX_MULTIPLIER, PricingService } from './pricing.service';

export interface ModelView {
  id: string;
  providerId: string;
  modelName: string;
  displayName: string;
  modelType: 'image' | 'video' | 'text' | 'audio' | '3d';
  enabled: boolean;
  isDefault: boolean;
  minPlanLevel: number;
  pricing: any;
  paramsSchema: any;
  description: string;
  sortOrder: number;
}

export interface AvailableModel extends ModelView {
  /** 该用户当前是否可调用 (effectivePlanLevel >= minPlanLevel 且模型/提供商均启用)。 */
  allowed: boolean;
  /** 基础参考价 (以 pricing.base 计, 前端展示; 精确价随参数由 /models/estimate 计) */
  baseCost: number;
}

export interface UpsertModelInput {
  id?: string;
  providerId: string;
  modelName: string;
  displayName?: string;
  modelType?: ModelView['modelType'];
  enabled?: boolean;
  isDefault?: boolean;
  minPlanLevel?: number;
  pricing?: any;
  paramsSchema?: any;
  description?: string;
  sortOrder?: number;
}

/** 生成受理时解析出的模型 + 提供商 (含密钥, 仅服务端内部)。 */
export interface ResolvedModel {
  model: any;
  provider: any;
}

@Injectable()
export class ModelsService {
  constructor(
    private readonly db: DatabaseService,
    private readonly users: UsersService,
    private readonly pricing: PricingService,
  ) {}

  // ── Admin CRUD ────────────────────────────────────────────────
  async listAll(providerId?: string): Promise<ModelView[]> {
    const rows = providerId
      ? await this.db.query<any[]>(
          'SELECT * FROM ai_models WHERE provider_id = ? ORDER BY model_type, sort_order, id',
          [providerId],
        )
      : await this.db.query<any[]>(
          'SELECT * FROM ai_models ORDER BY model_type, sort_order, id',
        );
    return rows.map(toView);
  }

  async createModel(input: UpsertModelInput): Promise<ModelView> {
    const id = (input.id ?? '').trim();
    if (!id) throw new BadRequestException('model id required');
    if (!input.providerId) throw new BadRequestException('providerId required');
    if (!input.modelName) throw new BadRequestException('modelName required');
    const prov = await this.db.query<any[]>('SELECT id FROM ai_providers WHERE id = ?', [input.providerId]);
    if (!prov.length) throw new BadRequestException('provider not found');
    const dup = await this.db.query<any[]>('SELECT id FROM ai_models WHERE id = ?', [id]);
    if (dup.length) throw new BadRequestException('model id already exists');

    const type = input.modelType ?? 'image';
    await this.db.transaction(async (conn) => {
      if (input.isDefault) {
        await conn.query('UPDATE ai_models SET is_default = 0 WHERE model_type = ?', [type]);
      }
      await conn.query(
        `INSERT INTO ai_models
          (id, provider_id, model_name, display_name, model_type, enabled, is_default,
           pricing_json, min_plan_level, params_schema_json, description, sort_order)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`,
        [
          id, input.providerId, input.modelName, input.displayName ?? input.modelName, type,
          input.enabled === false ? 0 : 1, input.isDefault ? 1 : 0,
          serializeRule(this.pricing.normalizeRule(input.pricing)),
          Number.isFinite(input.minPlanLevel as number) ? input.minPlanLevel : 0,
          serializeRule(this.pricing.normalizeParamsSchema(input.paramsSchema)),
          input.description ?? '', input.sortOrder ?? 0,
        ],
      );
    });
    return this.getView(id);
  }

  async updateModel(id: string, input: Partial<UpsertModelInput>): Promise<ModelView> {
    const cur = await this.getRaw(id);
    await this.db.transaction(async (conn) => {
      const sets: string[] = [];
      const vals: any[] = [];
      if (input.providerId !== undefined) { sets.push('provider_id = ?'); vals.push(input.providerId); }
      if (input.modelName !== undefined) { sets.push('model_name = ?'); vals.push(input.modelName); }
      if (input.displayName !== undefined) { sets.push('display_name = ?'); vals.push(input.displayName); }
      if (input.modelType !== undefined) { sets.push('model_type = ?'); vals.push(input.modelType); }
      if (input.enabled !== undefined) { sets.push('enabled = ?'); vals.push(input.enabled ? 1 : 0); }
      if (input.minPlanLevel !== undefined) { sets.push('min_plan_level = ?'); vals.push(input.minPlanLevel); }
      if (input.pricing !== undefined) { sets.push('pricing_json = ?'); vals.push(serializeRule(this.pricing.normalizeRule(input.pricing))); }
      if (input.paramsSchema !== undefined) { sets.push('params_schema_json = ?'); vals.push(serializeRule(this.pricing.normalizeParamsSchema(input.paramsSchema))); }
      if (input.description !== undefined) { sets.push('description = ?'); vals.push(input.description); }
      if (input.sortOrder !== undefined) { sets.push('sort_order = ?'); vals.push(input.sortOrder); }
      if (sets.length) {
        vals.push(id);
        await conn.query(`UPDATE ai_models SET ${sets.join(', ')} WHERE id = ?`, vals);
      }
      if (input.isDefault === true) {
        const type = input.modelType ?? cur.model_type;
        await conn.query('UPDATE ai_models SET is_default = 0 WHERE model_type = ?', [type]);
        await conn.query('UPDATE ai_models SET is_default = 1 WHERE id = ?', [id]);
      }
    });
    return this.getView(id);
  }

  async deleteModel(id: string): Promise<{ ok: true }> {
    const res: any = await this.db.query('DELETE FROM ai_models WHERE id = ?', [id]);
    if (res.affectedRows === 0) throw new NotFoundException('model not found');
    return { ok: true };
  }

  // ── User-facing ───────────────────────────────────────────────
  /** 列出所有启用模型 (启用的提供商下), 标注当前用户是否可调用 + 基础参考价。 */
  async listAvailable(userId: number, type?: string): Promise<AvailableModel[]> {
    const ctx = await this.users.getAuthzContext(userId);
    const params: any[] = [];
    let sql = `SELECT m.* FROM ai_models m
               JOIN ai_providers p ON p.id = m.provider_id
               WHERE m.enabled = 1 AND p.enabled = 1`;
    if (type) { sql += ' AND m.model_type = ?'; params.push(type); }
    sql += ' ORDER BY m.model_type, m.sort_order, m.id';
    const rows = await this.db.query<any[]>(sql, params);
    return rows.map((r) => {
      const v = toView(r);
      return {
        ...v,
        allowed: ctx.effectivePlanLevel >= v.minPlanLevel,
        baseCost: this.pricing.computeCost(r.pricing_json, {}),
      };
    });
  }

  /** 价格预估 (前端展示"预计消耗"): 校验访问权限 + 按参数算价。 */
  async estimate(userId: number, modelId: string, reqParams: Record<string, any>) {
    const ctx = await this.users.getAuthzContext(userId);
    const model = await this.getRaw(modelId);
    const cost = this.pricing.computeCost(model.pricing_json, reqParams ?? {});
    const allowed = ctx.effectivePlanLevel >= model.min_plan_level;
    return {
      modelId,
      cost,
      allowed,
      minPlanLevel: model.min_plan_level,
      effectivePlanLevel: ctx.effectivePlanLevel,
    };
  }

  /**
   * 生成受理: 解析模型(或按类型取默认) + 校验访问权限。
   * 返回含密钥的原始行, 仅服务端内部使用。
   */
  async resolveForGeneration(
    userId: number,
    modelId: string | undefined,
    type: 'image' | 'video' | 'text' | 'audio' | '3d',
  ): Promise<ResolvedModel> {
    const ctx = await this.users.getAuthzContext(userId);

    let model: any;
    if (modelId) {
      const rows = await this.db.query<any[]>('SELECT * FROM ai_models WHERE id = ?', [modelId]);
      if (!rows.length) throw new NotFoundException('model not found');
      model = rows[0];
      if (model.model_type !== type) {
        throw new BadRequestException(`model ${modelId} is ${model.model_type}, not ${type}`);
      }
    } else {
      const rows = await this.db.query<any[]>(
        'SELECT * FROM ai_models WHERE model_type = ? AND enabled = 1 ORDER BY is_default DESC, sort_order LIMIT 1',
        [type],
      );
      if (!rows.length) throw new NotFoundException(`no available model for type ${type}`);
      model = rows[0];
    }

    if (!model.enabled) throw new BadRequestException('model disabled');
    if (ctx.effectivePlanLevel < model.min_plan_level) {
      throw new ForbiddenException(
        `该模型需要更高套餐 (需权益等级 ${model.min_plan_level}, 当前 ${ctx.effectivePlanLevel})`,
      );
    }

    const provRows = await this.db.query<any[]>(
      'SELECT * FROM ai_providers WHERE id = ?',
      [model.provider_id],
    );
    if (!provRows.length) throw new BadRequestException('provider not found for model');
    const provider = provRows[0];
    if (!provider.enabled) throw new BadRequestException('provider disabled');

    return { model, provider };
  }

  computeCost(pricingJson: unknown, params: Record<string, any>): number {
    return this.pricing.computeCost(pricingJson, params);
  }

  /**
   * 管理端草稿试算: 不读库、不校验用户权益, 直接对表单当前规则算价并返回明细。
   *
   * 走的是与真实扣费完全相同的 PricingService, 所以"配置时看到的价"= "用户实际被扣的价",
   * 这是把手写 JSON 换成可视化表单后仍能让人放心的前提。
   */
  previewCost(pricing: unknown, params: Record<string, any> = {}) {
    const rule = this.pricing.normalizeRule(pricing);
    const detail = this.pricing.computeCostDetailed(rule, params ?? {});
    return { ...detail, normalizedPricing: rule, maxMultiplier: MAX_MULTIPLIER };
  }

  private async getRaw(id: string): Promise<any> {
    const rows = await this.db.query<any[]>('SELECT * FROM ai_models WHERE id = ?', [id]);
    if (!rows.length) throw new NotFoundException('model not found');
    return rows[0];
  }

  private async getView(id: string): Promise<ModelView> {
    return toView(await this.getRaw(id));
  }
}

function toView(r: any): ModelView {
  return {
    id: r.id,
    providerId: r.provider_id,
    modelName: r.model_name,
    displayName: r.display_name,
    modelType: r.model_type,
    enabled: !!r.enabled,
    isDefault: !!r.is_default,
    minPlanLevel: r.min_plan_level,
    pricing: parseJson(r.pricing_json),
    paramsSchema: parseJson(r.params_schema_json),
    description: r.description,
    sortOrder: r.sort_order,
  };
}

/** 清洗结果落库: null 存 SQL NULL (计价回落默认基础价), 否则存紧凑 JSON。 */
function serializeRule(rule: unknown): string | null {
  return rule != null ? JSON.stringify(rule) : null;
}

function parseJson(v: unknown): any {
  if (v == null) return null;
  if (typeof v === 'string') {
    try { return JSON.parse(v); } catch { return null; }
  }
  return v;
}
