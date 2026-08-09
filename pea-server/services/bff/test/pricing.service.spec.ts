import { PricingService, DEFAULT_BASE, MAX_MULTIPLIER } from '../src/modules/providers/pricing.service';
import { checkPricingRule, checkParamsSchema } from '../src/modules/providers/models.dto';

/**
 * 计价引擎单元基线测试。
 *
 * 背景: 管理端定价从"手写 pricing_json"改为可视化表单后, 引擎新增了
 *   ① computeCostDetailed —— 试算面板展示的明细, 必须与实扣价同源同结果;
 *   ② normalizeRule / normalizeParamsSchema —— 写库前的脏数据清洗;
 *   ③ DTO 层形状校验 —— API 仍对外暴露, 不能只靠表单自律。
 * 这三条一旦破防, 后果都是"线上按错价扣钱", 因此在此钉死行为。
 */
describe('PricingService', () => {
  const svc = new PricingService();

  describe('computeCost 基线行为 (不得回归)', () => {
    it('空规则回落默认基础价', () => {
      expect(svc.computeCost(null, {})).toBe(DEFAULT_BASE);
      expect(svc.computeCost(undefined, { size: '4K' })).toBe(DEFAULT_BASE);
      expect(svc.computeCost('not json', {})).toBe(DEFAULT_BASE);
    });

    it('命中档位累加, 未命中按 0', () => {
      const rule = { base: 10, tiers: { size: { '1K': 0, '2K': 5, '4K': 20 } } };
      expect(svc.computeCost(rule, { size: '1K' })).toBe(10);
      expect(svc.computeCost(rule, { size: '4K' })).toBe(30);
      expect(svc.computeCost(rule, { size: '8K' })).toBe(10);
      expect(svc.computeCost(rule, {})).toBe(10);
    });

    it('多维度加价叠加', () => {
      const rule = {
        base: 150,
        tiers: { size: { '2K': 0 }, duration: { '5': 0, '10': 140 } },
      };
      expect(svc.computeCost(rule, { size: '2K', duration: 10 })).toBe(290);
    });

    it('数量倍率生效并被钳制在 MAX_MULTIPLIER', () => {
      const rule = { base: 10, tiers: { size: { '4K': 20 } }, multiplier: 'n' };
      expect(svc.computeCost(rule, { size: '4K', n: 2 })).toBe(60);
      expect(svc.computeCost(rule, { size: '4K', n: 999 })).toBe(30 * MAX_MULTIPLIER);
      expect(svc.computeCost(rule, { size: '4K', n: 0 })).toBe(30);
      expect(svc.computeCost(rule, { size: '4K', n: 2.9 })).toBe(60); // 向下取整
    });

    it('最低消费 1 Tapies (免费也要留痕)', () => {
      expect(svc.computeCost({ base: 0 }, {})).toBe(1);
      expect(svc.computeCost({ base: 5, tiers: { promo: { on: -99 } } }, { promo: 'on' })).toBe(1);
    });

    it('接受 JSON 字符串形式 (DB 驱动可能返回字符串)', () => {
      expect(svc.computeCost('{"base":42}', {})).toBe(42);
    });
  });

  describe('computeCostDetailed 与 computeCost 同源', () => {
    it('明细的 cost 与 computeCost 完全一致', () => {
      const rule = { base: 10, tiers: { size: { '4K': 20 }, style: { anime: 3 } }, multiplier: 'n' };
      const params = { size: '4K', style: 'anime', n: 3 };
      expect(svc.computeCostDetailed(rule, params).cost).toBe(svc.computeCost(rule, params));
    });

    it('逐项明细可解释最终价', () => {
      const rule = { base: 10, tiers: { size: { '4K': 20 } }, multiplier: 'n' };
      const d = svc.computeCostDetailed(rule, { size: '4K', n: 2 });
      expect(d.base).toBe(10);
      expect(d.items).toEqual([{ dim: 'size', value: '4K', delta: 20, hit: true }]);
      expect(d.subtotal).toBe(30);
      expect(d.multiplierParam).toBe('n');
      expect(d.multiplier).toBe(2);
      expect(d.cost).toBe(60);
    });

    it('未命中档位也出现在明细里 (让管理员看见"配错了"而不是静默为 0)', () => {
      const d = svc.computeCostDetailed({ base: 10, tiers: { size: { '4K': 20 } } }, { size: '8K' });
      expect(d.items).toEqual([{ dim: 'size', value: '8K', delta: 0, hit: false }]);
      expect(d.cost).toBe(10);
    });
  });

  describe('normalizeRule 写库前清洗', () => {
    it('丢弃非法参数名与非数值加价', () => {
      const out = svc.normalizeRule({
        base: 10,
        tiers: {
          size: { '2K': 5, bad: 'NaN' as any },
          '2bad': { x: 1 },
          'has space': { x: 1 },
        },
      });
      expect(out).toEqual({ base: 10, tiers: { size: { '2K': 5 } } });
    });

    it('拦截原型污染键', () => {
      const out = svc.normalizeRule(
        JSON.parse('{"base":10,"tiers":{"__proto__":{"polluted":1},"size":{"2K":5}}}'),
      );
      expect(out).toEqual({ base: 10, tiers: { size: { '2K': 5 } } });
      expect(({} as any).polluted).toBeUndefined();
    });

    it('负基础价与超大数值被钳制', () => {
      expect(svc.normalizeRule({ base: -5 })).toEqual({ base: 0 });
      expect(svc.normalizeRule({ base: 1e12 })).toEqual({ base: 1_000_000 });
    });

    it('非法 multiplier 被丢弃而非落库', () => {
      expect(svc.normalizeRule({ base: 10, multiplier: '3n!' })).toEqual({ base: 10 });
      expect(svc.normalizeRule({ base: 10, multiplier: 'n' })).toEqual({ base: 10, multiplier: 'n' });
    });

    it('空规则归为 null (落库存 NULL, 计价回落默认价)', () => {
      expect(svc.normalizeRule({})).toBeNull();
      expect(svc.normalizeRule(null)).toBeNull();
      expect(svc.normalizeRule('garbage')).toBeNull();
    });

    it('清洗后的规则算出的价与清洗前一致 (清洗不改语义, 只去脏)', () => {
      const dirty = { base: 10, tiers: { size: { '4K': 20 }, '2bad': { x: 9999 } }, multiplier: 'n' };
      const clean = svc.normalizeRule(dirty);
      expect(svc.computeCost(clean, { size: '4K', n: 2 })).toBe(
        svc.computeCost(dirty, { size: '4K', n: 2 }),
      );
    });
  });

  describe('normalizeParamsSchema', () => {
    it('保留合法维度并去重, 丢弃对象元素', () => {
      const out = svc.normalizeParamsSchema({
        size: ['1K', '2K', '2K', { a: 1 }],
        n: [1, 2, 4],
        '9bad': ['x'],
      });
      expect(out).toEqual({ size: ['1K', '2K'], n: [1, 2, 4] });
    });

    it('空数组维度被丢弃; 全空返回 null', () => {
      expect(svc.normalizeParamsSchema({ size: [] })).toBeNull();
      expect(svc.normalizeParamsSchema([1, 2, 3])).toBeNull();
    });
  });

  describe('DTO 形状校验 (API 直连也拦得住)', () => {
    it('合法规则通过', () => {
      expect(checkPricingRule({ base: 10, tiers: { size: { '4K': 20 } }, multiplier: 'n' })).toBeNull();
      expect(checkPricingRule(null)).toBeNull();
    });

    it('数组 / 非法参数名 / 非数值加价被拒并给出人话原因', () => {
      expect(checkPricingRule([])).toContain('对象');
      expect(checkPricingRule({ tiers: { '2bad': { x: 1 } } })).toContain('非法');
      expect(checkPricingRule({ tiers: { size: { '4K': 'free' } } })).toContain('数字');
      expect(checkPricingRule({ base: -1 })).toContain('基础价');
      expect(checkPricingRule({ multiplier: 'n n' })).toContain('标识符');
    });

    it('参数选项校验', () => {
      expect(checkParamsSchema({ size: ['1K'], n: [1, 2] })).toBeNull();
      expect(checkParamsSchema({ size: '1K' })).toContain('数组');
      expect(checkParamsSchema({ size: [{ a: 1 }] })).toContain('字符串或数字');
    });
  });
});
