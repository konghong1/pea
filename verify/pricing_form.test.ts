// 可视化定价编辑器 —— 纯逻辑层 (pricingForm.ts) 单测
//
// 直接 import 生产源码 pea-server/web/src/components/admin/pricingForm，
// 不复制逻辑，避免「测试与实现双写漂移」。
//
// 这组测试把「两份 JSON（pricing / params_schema）收敛成同一套表单、且不丢维度」
// 从设计意图钉成可断言的不变量：
//   - toWire: 表单 → (pricing, paramsSchema)，数字档位输出数字数组、空维度/非法名丢弃
//   - toFormValue: (pricing, paramsSchema) → 表单，按两边维度并集还原，历史脏数据不丢
//   - validateForm: 只拦「保存后必然出问题」的情况，错误信息是人话
//   - 原型污染防护: 维度名 __proto__/constructor/prototype 必须被丢弃
//
// 运行：node verify/run-ts-tests.mjs pricing_form
import {
  toWire,
  toFormValue,
  validateForm,
  defaultPreviewParams,
  summarizePricing,
  isSafeDimName,
  MAX_DIMS,
  MAX_TIERS_PER_DIM,
  MAX_PRICE,
} from '../pea-server/web/src/components/admin/pricingForm';

let failures = 0;
function check(cond: boolean, msg: string) {
  if (cond) {
    console.log('  PASS  ', msg);
  } else {
    console.error('  FAIL  ', msg);
    failures++;
  }
}
function eq(a: unknown, b: unknown, msg: string) {
  check(JSON.stringify(a) === JSON.stringify(b), `${msg}  (得到 ${JSON.stringify(a)}，期望 ${JSON.stringify(b)})`);
}

// ─────────────────────────────────────────────────────────────────────────────
console.log('— toWire：表单 → (pricing, params_schema) —');

{
  const form = {
    base: 10,
    dims: [
      {
        uid: 'd1',
        key: 'size',
        tiers: [
          { uid: 't1', value: '1K', delta: 0 },
          { uid: 't2', value: '2K', delta: 5 },
          { uid: 't3', value: '4K', delta: 20 },
        ],
      },
      {
        uid: 'd2',
        key: 'quality',
        tiers: [
          { uid: 't4', value: 'standard', delta: 0 },
          { uid: 't5', value: 'high', delta: 8 },
        ],
      },
    ],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  };
  const { pricing, paramsSchema } = toWire(form);

  eq(pricing.base, 10, '基础价透传');
  eq(
    pricing.tiers,
    {
      size: { '1K': 0, '2K': 5, '4K': 20 },
      quality: { standard: 0, high: 8 },
    },
    'tiers 结构与加价额正确',
  );
  eq(
    paramsSchema,
    {
      size: ['1K', '2K', '4K'],
      quality: ['standard', 'high'],
    },
    'params_schema 含全部维度与取值',
  );
}

// 数字档位 → params_schema 输出数字数组（与既有种子数据 n:[1,2,4] 口径一致）
console.log('— toWire：纯数字档位输出 number[] —');
{
  const { paramsSchema } = toWire({
    base: 10,
    dims: [
      { uid: 'd1', key: 'dur', tiers: [{ uid: 't1', value: '5', delta: 0 }, { uid: 't2', value: '10', delta: 3 }] },
    ],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  });
  eq(paramsSchema?.dur, [5, 10], '纯数字取值 → number 数组');
}

// 空维度 / 空档位 / 非法名 丢弃：宁可少存，也不让残缺进入计费真相源
console.log('— toWire：丢弃空维度 / 空档位 / 非法参数名 —');
{
  const { pricing, paramsSchema } = toWire({
    base: 10,
    dims: [
      { uid: 'd1', key: 'good', tiers: [{ uid: 't1', value: 'a', delta: 2 }] },
      { uid: 'd2', key: 'empty', tiers: [] }, // 空档位 → 整维丢弃
      { uid: 'd3', key: '1bad', tiers: [{ uid: 't2', value: 'x', delta: 1 }] }, // 非法名 → 丢弃
      { uid: 'd4', key: 'dup', tiers: [{ uid: 't3', value: '', delta: 1 }, { uid: 't4', value: 'b', delta: 1 }] }, // 空档位值 → 跳过
    ],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  });
  check(!('empty' in (pricing.tiers ?? {})), '空档位维度被丢弃');
  check(!('1bad' in (pricing.tiers ?? {})), '非法名维度被丢弃');
  eq(pricing.tiers, { good: { a: 2 }, dup: { b: 1 } }, '仅合法档位进入 tiers');
  eq(paramsSchema, { good: ['a'], dup: ['b'] }, 'params_schema 同步只留合法维度');
}

// 数量倍率 → pricing.multiplier + params_schema[mKey]（不进 tiers，因为是乘不是加）
console.log('— toWire：数量倍率 —');
{
  const { pricing, paramsSchema } = toWire({
    base: 10,
    dims: [{ uid: 'd1', key: 'size', tiers: [{ uid: 't1', value: '4K', delta: 20 }] }],
    multiplierEnabled: true,
    multiplierKey: 'n',
    multiplierOptions: ['1', '2', '4'],
  });
  check(pricing.multiplier === 'n', 'multiplier 写入 n');
  eq(paramsSchema?.n, [1, 2, 4], '数量可选值进 params_schema、且不进 tiers');
  check(!('n' in (pricing.tiers ?? {})), '数量维度不进 tiers');
}

// 原型污染防护：维度名 __proto__ / constructor / prototype 必须被丢弃
console.log('— toWire：原型污染防护 —');
{
  const evil: any = {
    base: 10,
    dims: [
      { uid: 'd1', key: '__proto__', tiers: [{ uid: 't1', value: 'a', delta: 99 }] },
      { uid: 'd2', key: 'constructor', tiers: [{ uid: 't2', value: 'b', delta: 1 }] },
      { uid: 'd3', key: 'prototype', tiers: [{ uid: 't3', value: 'c', delta: 1 }] },
      { uid: 'd4', key: 'ok', tiers: [{ uid: 't4', value: 'd', delta: 1 }] },
    ],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  };
  const { pricing } = toWire(evil);
  const tiers = pricing.tiers ?? {};
  const hasOwn = Object.prototype.hasOwnProperty.call.bind(Object.prototype.hasOwnProperty);
  check(!hasOwn(tiers, '__proto__'), '__proto__ 维度被丢弃');
  check(!hasOwn(tiers, 'constructor'), 'constructor 维度被丢弃');
  check(!hasOwn(tiers, 'prototype'), 'prototype 维度被丢弃');
  eq(pricing.tiers, { ok: { d: 1 } }, '仅安全维度进入 tiers');
}

// ─────────────────────────────────────────────────────────────────────────────
console.log('— toFormValue：反序列化（维度并集，不丢历史配置）—');

// ① 两边维度一致
{
  const { pricing, paramsSchema } = toWire({
    base: 10,
    dims: [{ uid: 'd1', key: 'size', tiers: [{ uid: 't1', value: '2K', delta: 5 }] }],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  });
  const form = toFormValue(pricing, paramsSchema, 'image');
  eq(form.base, 10, 'base 还原');
  check(form.dims.length === 1 && form.dims[0].key === 'size', 'size 维度还原');
  eq(form.dims[0].tiers, [{ uid: form.dims[0].tiers[0].uid, value: '2K', delta: 5 }], '档位值/加价还原');
}

// ② 只在 params_schema 里有的值 → 档位加价按 0 补齐（用户能选、不加价）
{
  const pricing = { base: 10, tiers: { size: { '2K': 5 } } };
  const paramsSchema = { size: ['1K', '2K', '4K'] };
  const form = toFormValue(pricing, paramsSchema);
  const tiers = form.dims[0].tiers;
  eq(tiers.map((t) => t.value), ['1K', '2K', '4K'], '三个取值都列出');
  eq(tiers.map((t) => t.delta), [0, 5, 0], 'schema 多出的值加价补 0');
}

// ③ 只在 pricing.tiers 里有的值 → 也列出（已生效加价，管理员不能看不到）
{
  const pricing = { base: 10, tiers: { size: { '2K': 5, '8K': 99 } } };
  const paramsSchema = { size: ['2K'] };
  const form = toFormValue(pricing, paramsSchema);
  eq(form.dims[0].tiers.map((t) => t.value), ['2K', '8K'], 'tiers 多出的 8K 也列出');
}

// ④ 全新模型（无 pricing 无 dims）→ 按类型给推荐维度
{
  const form = toFormValue(null, null, 'image');
  eq(form.dims.map((d) => d.key), ['size'], 'image 默认推荐 size 维度');
  eq(form.dims[0].tiers.map((t) => t.value), ['1K', '2K', '4K'], 'image size 推荐值正确');
  const formVideo = toFormValue(null, null, 'video');
  eq(formVideo.dims.map((d) => d.key), ['size', 'duration'], 'video 推荐 size+duration');
}

// ─────────────────────────────────────────────────────────────────────────────
console.log('— 往返一致：form → wire → form → wire 稳定 —');
{
  const form1 = toFormValue(
    { base: 12, tiers: { size: { '1K': 0, '4K': 20 }, quality: { high: 8 } }, multiplier: 'n' },
    { size: ['1K', '4K'], quality: ['standard', 'high'], n: [1, 2] },
    'image',
  );
  form1.multiplierOptions = ['1', '2'];
  const wire1 = toWire(form1);
  const form2 = toFormValue(wire1.pricing, wire1.paramsSchema, 'image');
  const wire2 = toWire(form2);
  eq(wire2.pricing, wire1.pricing, 'pricing 往返稳定');
  eq(wire2.paramsSchema, wire1.paramsSchema, 'params_schema 往返稳定');
}

// ─────────────────────────────────────────────────────────────────────────────
console.log('— validateForm：人话错误 —');

check(validateForm({ base: -1, dims: [], multiplierEnabled: false, multiplierKey: 'n', multiplierOptions: ['1'] }).length > 0, '负基础价被拦截');
check(validateForm({ base: 'x', dims: [], multiplierEnabled: false, multiplierKey: 'n', multiplierOptions: ['1'] } as any).some((e) => e.includes('基础价')), '非数字基础价被拦截');
check(
  validateForm({
    base: 10,
    dims: [{ uid: 'd1', key: '9bad', tiers: [{ uid: 't1', value: 'a', delta: 0 }] }],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  }).some((e) => e.includes('非法')),
  '非法参数名被拦截',
);
check(
  validateForm({
    base: 10,
    dims: [
      { uid: 'd1', key: 'size', tiers: [{ uid: 't1', value: 'a', delta: 0 }] },
      { uid: 'd2', key: 'size', tiers: [{ uid: 't2', value: 'b', delta: 0 }] },
    ],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  }).some((e) => e.includes('重复')),
  '重复参数名被拦截',
);
check(
  validateForm({
    base: 10,
    dims: [{ uid: 'd1', key: 'size', tiers: [{ uid: 't1', value: 'a', delta: 0 }] }],
    multiplierEnabled: true,
    multiplierKey: 'size',
    multiplierOptions: ['1', '2'],
  }).some((e) => e.includes('不能同时作为数量倍率')),
  '数量倍率与加价维度冲突被拦截',
);
check(
  validateForm({
    base: 10,
    dims: [{ uid: 'd1', key: 'size', tiers: [{ uid: 't1', value: 'a', delta: 0 }] }],
    multiplierEnabled: true,
    multiplierKey: 'n',
    multiplierOptions: [],
  }).some((e) => e.includes('数量倍率至少要')),
  '数量倍率无可选值被拦截',
);
// 合法表单零错误
check(
  validateForm({
    base: 10,
    dims: [{ uid: 'd1', key: 'size', tiers: [{ uid: 't1', value: '4K', delta: 20 }] }],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  }).length === 0,
  '合法表单零错误',
);

// ─────────────────────────────────────────────────────────────────────────────
console.log('— defaultPreviewParams：取每个维度最贵档 —');
{
  const form = toFormValue(
    { base: 10, tiers: { size: { '1K': 0, '4K': 20 }, quality: { standard: 0, high: 8 } }, multiplier: 'n' },
    { size: ['1K', '4K'], quality: ['standard', 'high'], n: [1, 4] },
    'image',
  );
  form.multiplierOptions = ['1', '4'];
  const picks = defaultPreviewParams(form);
  eq(picks, { size: '4K', quality: 'high', n: '1' }, '每个维度取最贵档、数量取首个');
}

// ─────────────────────────────────────────────────────────────────────────────
console.log('— summarizePricing：表格摘要 —');
{
  check(summarizePricing(null) === '默认 10', '无定价显示默认价');
  eq(
    summarizePricing({ base: 10, tiers: { size: { '4K': 20 } }, multiplier: 'n' }),
    '基础 10 · size: 4K+20 · ×n',
    '摘要含基础价/档位加价/倍率',
  );
}

// ─────────────────────────────────────────────────────────────────────────────
console.log('— isSafeDimName：边界 —');
check(isSafeDimName('size') && isSafeDimName('_a1') && !isSafeDimName('9x') && !isSafeDimName('__proto__') && !isSafeDimName('a b'), '合法/非法名判定正确');

// ─────────────────────────────────────────────────────────────────────────────
console.log('— 边界常量与上限 —');
{
  // 超过 MAX_TIERS_PER_DIM 的档位被截断
  const manyTiers = Array.from({ length: MAX_TIERS_PER_DIM + 5 }, (_, i) => ({ uid: `t${i}`, value: `v${i}`, delta: 0 }));
  const { paramsSchema } = toWire({
    base: 10,
    dims: [{ uid: 'd1', key: 'size', tiers: manyTiers }],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  });
  check((paramsSchema?.size?.length ?? 0) === MAX_TIERS_PER_DIM, `档位数被截断到 ${MAX_TIERS_PER_DIM}`);

  // 超过 MAX_DIMS 的维度被截断
  const manyDims = Array.from({ length: MAX_DIMS + 3 }, (_, i) => ({ uid: `d${i}`, key: `dim${i}`, tiers: [{ uid: `t${i}`, value: 'a', delta: 0 }] }));
  const w = toWire({ base: 10, dims: manyDims, multiplierEnabled: false, multiplierKey: 'n', multiplierOptions: ['1'] });
  check(Object.keys(w.paramsSchema ?? {}).length === MAX_DIMS, `维度数被截断到 ${MAX_DIMS}`);

  // 加价超出 MAX_PRICE 被钳制
  const clamped = toWire({
    base: 10,
    dims: [{ uid: 'd1', key: 'size', tiers: [{ uid: 't1', value: 'x', delta: MAX_PRICE + 5000 }] }],
    multiplierEnabled: false,
    multiplierKey: 'n',
    multiplierOptions: ['1'],
  });
  eq(clamped.pricing.tiers?.size.x, MAX_PRICE, `加价被钳制到 ${MAX_PRICE}`);
}

// ─────────────────────────────────────────────────────────────────────────────
console.log('');
if (failures > 0) {
  console.error(`❌ ${failures} 条断言失败`);
  process.exit(1);
} else {
  console.log('✅ pricing_form 全部断言通过');
}
