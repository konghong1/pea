import { Injectable } from '@nestjs/common';

export interface PricingRule {
  base?: number;
  /** 各参数维度的加价档: { size: { '2K': 5, '4K': 20 }, duration: { '10': 40 } } */
  tiers?: Record<string, Record<string, number>>;
  /** 数量倍率参数名 (最终价 = (base + Σ命中 delta) * clamp(req[multiplier])) */
  multiplier?: string;
}

const DEFAULT_BASE = 10;
const MAX_MULTIPLIER = 8; // 防止客户端传天量 n 触发异常预扣

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
    const rule = this.parse(pricingJson);
    const base = this.num(rule.base, DEFAULT_BASE);

    let delta = 0;
    const tiers = rule.tiers ?? {};
    for (const [dim, table] of Object.entries(tiers)) {
      if (!table || typeof table !== 'object') continue;
      const val = params?.[dim];
      if (val === undefined || val === null) continue;
      const hit = (table as Record<string, number>)[String(val)];
      if (typeof hit === 'number' && Number.isFinite(hit)) delta += hit;
    }

    let mult = 1;
    if (rule.multiplier) {
      const raw = Number(params?.[rule.multiplier]);
      if (Number.isFinite(raw) && raw >= 1) {
        mult = Math.min(MAX_MULTIPLIER, Math.floor(raw));
      }
    }

    const cost = Math.floor((base + delta) * mult);
    return Math.max(1, cost);
  }

  private parse(pricingJson: unknown): PricingRule {
    if (!pricingJson) return {};
    if (typeof pricingJson === 'string') {
      try {
        return JSON.parse(pricingJson) as PricingRule;
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
