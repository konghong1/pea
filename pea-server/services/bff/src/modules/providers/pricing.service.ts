import { Injectable } from '@nestjs/common';

export interface PricingRule {
  base?: number;
  /** 各参数维度的加价档: { size: { '2K': 5, '4K': 20 }, duration: { '10': 40 } } */
  tiers?: Record<string, Record<string, number>>;
  /** 数量倍率参数名 (最终价 = (base + Σ命中 delta) * clamp(req[multiplier])) */
  multiplier?: string;
}

/** 计价明细单项 (供管理端"实时试算"逐条展示, 让非工程人员看懂钱从哪来)。 */
export interface CostBreakdownItem {
  /** 参数维度名, 如 size / duration */
  dim: string;
  /** 本次请求该维度的取值 (字符串化) */
  value: string;
  /** 命中的加价额; 未命中为 0 */
  delta: number;
  /** 是否在 tiers 表里命中了档位 */
  hit: boolean;
}

export interface CostBreakdown {
  /** 最终价 (与 computeCost 完全一致) */
  cost: number;
  /** 基础价 (缺省 DEFAULT_BASE) */
  base: number;
  /** 各维度加价明细 */
  items: CostBreakdownItem[];
  /** 倍率前小计 = base + Σdelta */
  subtotal: number;
  /** 数量倍率参数名 (未配置为 null) */
  multiplierParam: string | null;
  /** 实际生效倍率 (已按 [1, MAX_MULTIPLIER] 钳制并向下取整) */
  multiplier: number;
}

export const DEFAULT_BASE = 10;
/** 防止客户端传天量 n 触发异常预扣 */
export const MAX_MULTIPLIER = 8;

/** 单个模型最多可配的参数维度数 (防止表单/JSON 灌入超大对象) */
export const MAX_DIMS = 12;
/** 单个维度最多可配的档位数 */
export const MAX_TIERS_PER_DIM = 40;
/** 基础价 / 加价额的绝对值上限 */
export const MAX_PRICE = 1_000_000;
/** 参数维度名合法格式 (与下游 provider 参数名对齐, 仅允许标识符) */
export const DIM_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]{0,31}$/;
/** 原型污染保留字: 这些名字赋值到普通对象上会改写原型链而非新增属性 */
const RESERVED_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

/** 维度名是否可安全用作对象键。 */
export function isSafeDimName(name: string): boolean {
  return DIM_NAME_RE.test(name) && !RESERVED_KEYS.has(name);
}

/**
 * 计费引擎 (服务端权威, 对应"按参数动态计价")。
 *
 * 安全red线: 客户端**不得**决定价格; 一切以模型 pricing_json + 请求参数在此计算为准。
 * 纯函数, 无副作用, 便于单测与并发安全 (无共享状态)。
 */
@Injectable()
export class PricingService {
  /**
   * 计算一次生成的 Tapies 成本。
   * @param pricingJson  模型的 pricing_json (可为 string / object / null)
   * @param params       本次请求参数 (size / duration / n 等)
   */
  computeCost(pricingJson: unknown, params: Record<string, any> = {}): number {
    return this.computeCostDetailed(pricingJson, params).cost;
  }

  /**
   * 与 computeCost 同源同结果, 额外返回逐项明细。
   *
   * 仅用于展示 (管理端试算 / 用户端"为什么这么贵"), 真实扣费仍走 computeCost,
   * 两者共用同一段算法, 不存在"预览价与实扣价不一致"的漂移风险。
   */
  computeCostDetailed(
    pricingJson: unknown,
    params: Record<string, any> = {},
  ): CostBreakdown {
    const rule = this.parse(pricingJson);
    const base = this.num(rule.base, DEFAULT_BASE);

    const items: CostBreakdownItem[] = [];
    let delta = 0;
    const tiers = rule.tiers ?? {};
    for (const [dim, table] of Object.entries(tiers)) {
      if (!table || typeof table !== 'object') continue;
      const val = params?.[dim];
      if (val === undefined || val === null) continue;
      const hit = (table as Record<string, number>)[String(val)];
      const ok = typeof hit === 'number' && Number.isFinite(hit);
      if (ok) delta += hit;
      items.push({ dim, value: String(val), delta: ok ? hit : 0, hit: ok });
    }

    let mult = 1;
    if (rule.multiplier) {
      const raw = Number(params?.[rule.multiplier]);
      if (Number.isFinite(raw) && raw >= 1) {
        mult = Math.min(MAX_MULTIPLIER, Math.floor(raw));
      }
    }

    const subtotal = base + delta;
    const cost = Math.max(1, Math.floor(subtotal * mult));
    return {
      cost,
      base,
      items,
      subtotal,
      multiplierParam: rule.multiplier ?? null,
      multiplier: mult,
    };
  }

  /**
   * 写库前清洗: 只保留引擎认识的字段, 并对数值/键名做边界钳制。
   *
   * 存在意义: 管理端表单与 API 都可能塞进脏数据 (超长键、NaN、嵌套对象、原型污染键)。
   * 数据库里的 pricing_json 是计费真相源, 脏进去就会变成线上事故, 因此在入口一次性收敛。
   * 返回 null 表示"无有效规则", 落库存 NULL, 计价时走 DEFAULT_BASE。
   */
  normalizeRule(input: unknown): PricingRule | null {
    const rule = this.parse(input);
    const out: PricingRule = {};

    if (rule.base !== undefined && rule.base !== null) {
      const b = Number(rule.base);
      if (Number.isFinite(b)) out.base = clamp(Math.floor(b), 0, MAX_PRICE);
    }

    const tiers = rule.tiers;
    if (tiers && typeof tiers === 'object' && !Array.isArray(tiers)) {
      const cleanTiers: Record<string, Record<string, number>> = {};
      let dimCount = 0;
      for (const [rawDim, table] of Object.entries(tiers)) {
        if (dimCount >= MAX_DIMS) break;
        const dim = String(rawDim).trim();
        if (!isSafeDimName(dim)) continue;
        if (!table || typeof table !== 'object' || Array.isArray(table)) continue;

        const cleanTable: Record<string, number> = {};
        let optCount = 0;
        for (const [rawKey, rawVal] of Object.entries(table)) {
          if (RESERVED_KEYS.has(String(rawKey))) continue;
          if (optCount >= MAX_TIERS_PER_DIM) break;
          const key = String(rawKey).trim();
          if (!key || key.length > 64) continue;
          const n = Number(rawVal);
          if (!Number.isFinite(n)) continue;
          cleanTable[key] = clamp(Math.floor(n), -MAX_PRICE, MAX_PRICE);
          optCount++;
        }
        if (Object.keys(cleanTable).length) {
          cleanTiers[dim] = cleanTable;
          dimCount++;
        }
      }
      if (Object.keys(cleanTiers).length) out.tiers = cleanTiers;
    }

    if (rule.multiplier != null) {
      const m = String(rule.multiplier).trim();
      if (isSafeDimName(m)) out.multiplier = m;
    }

    return Object.keys(out).length ? out : null;
  }

  /**
   * 清洗前端参数选择器 schema: { size: ['1K','2K'], n: [1,2,4] }。
   *
   * 与 pricing 同一个表单产出, 因此在同一层收敛, 保证两者维度不漂移。
   */
  normalizeParamsSchema(input: unknown): Record<string, (string | number)[]> | null {
    const src = this.parse(input) as unknown;
    if (!src || typeof src !== 'object' || Array.isArray(src)) return null;

    const out: Record<string, (string | number)[]> = {};
    let dimCount = 0;
    for (const [rawDim, rawList] of Object.entries(src as Record<string, unknown>)) {
      if (dimCount >= MAX_DIMS) break;
      const dim = String(rawDim).trim();
      if (!isSafeDimName(dim)) continue;
      if (!Array.isArray(rawList)) continue;

      const list: (string | number)[] = [];
      const seen = new Set<string>();
      for (const item of rawList) {
        if (list.length >= MAX_TIERS_PER_DIM) break;
        if (item === null || item === undefined) continue;
        if (typeof item === 'object') continue;
        const val = typeof item === 'number' ? item : String(item).trim();
        if (val === '') continue;
        if (typeof val === 'number' && !Number.isFinite(val)) continue;
        const k = String(val);
        if (k.length > 64 || seen.has(k)) continue;
        seen.add(k);
        list.push(val);
      }
      if (list.length) {
        out[dim] = list;
        dimCount++;
      }
    }
    return Object.keys(out).length ? out : null;
  }

  private parse(pricingJson: unknown): PricingRule {
    if (!pricingJson) return {};
    if (typeof pricingJson === 'string') {
      try {
        const v = JSON.parse(pricingJson);
        return v && typeof v === 'object' ? (v as PricingRule) : {};
      } catch {
        return {};
      }
    }
    if (typeof pricingJson === 'object') return pricingJson as PricingRule;
    return {};
  }

  private num(v: unknown, dflt: number): number {
    const n = Number(v);
    return Number.isFinite(n) && n >= 0 ? n : dflt;
  }
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}
