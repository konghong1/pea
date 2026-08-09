import {
  IsBoolean,
  IsOptional,
  IsString,
  IsIn,
  IsInt,
  Min,
  MaxLength,
  IsObject,
  Validate,
  ValidatorConstraint,
  ValidatorConstraintInterface,
  ValidationArguments,
} from 'class-validator';
import { DIM_NAME_RE, MAX_DIMS, MAX_PRICE, MAX_TIERS_PER_DIM } from './pricing.service';

/**
 * pricing_json 结构校验。
 *
 * 之前这里是裸 `any`, 任何形状的 JSON 都能落进计费真相源 —— 管理端换成可视化表单后,
 * 表单只会产出合法结构, 但 API 仍对外暴露, 因此校验必须留在服务端而非表单里。
 * 只判"形状与边界"; 数值钳制与脏字段丢弃由 PricingService.normalizeRule 兜底。
 *
 * 注意: 约束类在 class-validator 中是**单例**, 错误信息绝不能存实例字段
 * (并发请求会互相串消息), 因此校验逻辑抽成下面的纯函数, validate 与 defaultMessage 共用。
 */
@ValidatorConstraint({ name: 'IsPricingRule', async: false })
export class PricingRuleConstraint implements ValidatorConstraintInterface {
  validate(value: unknown): boolean {
    return checkPricingRule(value) === null;
  }

  defaultMessage(args: ValidationArguments): string {
    return checkPricingRule(args?.value) ?? '定价规则格式非法';
  }
}

/**
 * params_schema_json 结构校验: { size: ['1K','2K'], n: [1,2,4] }。
 * 与 pricing 由同一张表单产出, 因此边界口径保持一致。
 */
@ValidatorConstraint({ name: 'IsParamsSchema', async: false })
export class ParamsSchemaConstraint implements ValidatorConstraintInterface {
  validate(value: unknown): boolean {
    return checkParamsSchema(value) === null;
  }

  defaultMessage(args: ValidationArguments): string {
    return checkParamsSchema(args?.value) ?? '参数选项格式非法';
  }
}

/** 校验定价规则形状; 返回首个错误说明, 合法返回 null。 */
export function checkPricingRule(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'object' || Array.isArray(value)) return '定价规则必须是对象';
  const rule = value as Record<string, unknown>;

  if (rule.base !== undefined && rule.base !== null) {
    const b = Number(rule.base);
    if (!Number.isFinite(b) || b < 0 || b > MAX_PRICE) {
      return `基础价必须是 0 ~ ${MAX_PRICE} 之间的数字`;
    }
  }

  if (rule.multiplier !== undefined && rule.multiplier !== null) {
    if (typeof rule.multiplier !== 'string' || !DIM_NAME_RE.test(rule.multiplier)) {
      return '数量倍率参数名必须是合法标识符 (字母或下划线开头)';
    }
  }

  const tiers = rule.tiers;
  if (tiers === undefined || tiers === null) return null;
  if (typeof tiers !== 'object' || Array.isArray(tiers)) return '加价档 tiers 必须是对象';

  const dims = Object.entries(tiers as Record<string, unknown>);
  if (dims.length > MAX_DIMS) return `参数维度最多 ${MAX_DIMS} 个`;
  for (const [dim, table] of dims) {
    if (!DIM_NAME_RE.test(dim)) {
      return `参数名 "${dim}" 非法 (仅允许字母/数字/下划线, 且不以数字开头)`;
    }
    if (!table || typeof table !== 'object' || Array.isArray(table)) {
      return `参数 "${dim}" 的档位表必须是对象`;
    }
    const entries = Object.entries(table as Record<string, unknown>);
    if (entries.length > MAX_TIERS_PER_DIM) {
      return `参数 "${dim}" 的档位最多 ${MAX_TIERS_PER_DIM} 个`;
    }
    for (const [key, delta] of entries) {
      if (!key || key.length > 64) return `参数 "${dim}" 存在空档位值或档位值过长`;
      const n = Number(delta);
      if (!Number.isFinite(n) || Math.abs(n) > MAX_PRICE) {
        return `参数 "${dim}" 档位 "${key}" 的加价必须是数字`;
      }
    }
  }
  return null;
}

/** 校验参数选项形状; 返回首个错误说明, 合法返回 null。 */
export function checkParamsSchema(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'object' || Array.isArray(value)) return '参数选项必须是对象';

  const dims = Object.entries(value as Record<string, unknown>);
  if (dims.length > MAX_DIMS) return `参数维度最多 ${MAX_DIMS} 个`;
  for (const [dim, list] of dims) {
    if (!DIM_NAME_RE.test(dim)) return `参数名 "${dim}" 非法`;
    if (!Array.isArray(list)) return `参数 "${dim}" 的可选值必须是数组`;
    if (list.length > MAX_TIERS_PER_DIM) {
      return `参数 "${dim}" 的可选值最多 ${MAX_TIERS_PER_DIM} 个`;
    }
    for (const item of list) {
      if (item !== null && typeof item === 'object') {
        return `参数 "${dim}" 的可选值只能是字符串或数字`;
      }
    }
  }
  return null;
}

export class CreateModelDto {
  @IsString() @MaxLength(64)
  id: string;

  @IsString() @MaxLength(64)
  providerId: string;

  @IsString() @MaxLength(200)
  modelName: string;

  @IsOptional() @IsString() @MaxLength(200)
  displayName?: string;

  @IsOptional() @IsIn(['image', 'video', 'text', 'audio', '3d'])
  modelType?: 'image' | 'video' | 'text' | 'audio' | '3d';

  @IsOptional() @IsBoolean()
  enabled?: boolean;

  @IsOptional() @IsBoolean()
  isDefault?: boolean;

  @IsOptional() @IsInt() @Min(0)
  minPlanLevel?: number;

  @IsOptional() @Validate(PricingRuleConstraint)
  pricing?: any;

  @IsOptional() @Validate(ParamsSchemaConstraint)
  paramsSchema?: any;

  @IsOptional() @IsString() @MaxLength(500)
  description?: string;

  @IsOptional() @IsInt()
  sortOrder?: number;
}

export class UpdateModelDto {
  @IsOptional() @IsString() @MaxLength(64)
  providerId?: string;

  @IsOptional() @IsString() @MaxLength(200)
  modelName?: string;

  @IsOptional() @IsString() @MaxLength(200)
  displayName?: string;

  @IsOptional() @IsIn(['image', 'video', 'text', 'audio', '3d'])
  modelType?: 'image' | 'video' | 'text' | 'audio' | '3d';

  @IsOptional() @IsBoolean()
  enabled?: boolean;

  @IsOptional() @IsBoolean()
  isDefault?: boolean;

  @IsOptional() @IsInt() @Min(0)
  minPlanLevel?: number;

  @IsOptional() @Validate(PricingRuleConstraint)
  pricing?: any;

  @IsOptional() @Validate(ParamsSchemaConstraint)
  paramsSchema?: any;

  @IsOptional() @IsString() @MaxLength(500)
  description?: string;

  @IsOptional() @IsInt()
  sortOrder?: number;
}

export class EstimateDto {
  @IsString()
  modelId: string;

  @IsOptional() @IsObject()
  params?: Record<string, any>;
}

/**
 * 管理端"实时试算": 对**尚未落库的草稿规则**算价。
 *
 * 与 /models/estimate 的区别: 后者按 modelId 读库并校验用户权益, 新建模型时无从谈起;
 * 这里直接吃表单当前值, 让管理员边配边看到真实价格 —— 这正是取代手写 JSON 的关键一环。
 */
export class PreviewCostDto {
  @IsOptional() @Validate(PricingRuleConstraint)
  pricing?: any;

  @IsOptional() @IsObject()
  params?: Record<string, any>;
}
