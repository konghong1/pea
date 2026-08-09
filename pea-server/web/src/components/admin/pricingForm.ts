import type { PricingRule } from '../../api/catalog';

/**
 * 可视化定价编辑器的**纯逻辑层** (无 DOM、无 React、无网络)。
 *
 * 背景: 模型定价原先靠管理员手写 pricing_json, 且 params_schema_json 另有一份、
 * 两者的参数维度经常对不上 (定价里配了 4K、参数选择器里却没有 4K, 用户永远选不到)。
 * 这里把两份 JSON 收敛成同一个表单模型: 一个"参数维度"同时决定
 *   ① 用户能选哪些值 (params_schema)  ② 每个值加多少钱 (pricing.tiers)
 * 从根上消除漂移。
 *
 * 组件只负责渲染与交互, 所有转换/校验都在此处, 便于零依赖单测直接 import 生产源码。
 */

/** 一个档位: 参数取值 + 相对基础价的加价额。 */
export interface TierRow {
  /** 稳定 key, 仅供 React list 使用, 不参与序列化 */
  uid: string;
  /** 参数取值, 如 '4K' / '10' */
  value: string;
  /** 加价额 (可为 0, 也可为负数做促销) */
  delta: number;
}

/** 一个参数维度, 如 size / duration。 */
export interface DimRow {
  uid: string;
  /** 参数名 (下游 provider 实际收到的 key) */
  key: string;
  tiers: TierRow[];
}

/** 表单的完整状态 —— 保存时转成 pricing + paramsSchema 两份 JSON。 */
export interface PricingFormValue {
  base: number;
  dims: DimRow[];
  /** 是否启用数量倍率 */
  multiplierEnabled: boolean;
  /** 数量参数名, 默认 n */
  multiplierKey: string;
  /** 数量可选值 (只进 params_schema, 不进 tiers —— 它是乘不是加) */
  multiplierOptions: string[];
}

export interface WireValue {
  pricing: PricingRule | null;
  paramsSchema: Record<string, (string | number)[]> | null;
}

/** 与后端 pricing.service.ts 保持一致的边界 (超出即被服务端裁掉, 前端提前拦下给出提示)。 */
export const MAX_DIMS = 12;
export const MAX_TIERS_PER_DIM = 40;
export const MAX_PRICE = 1_000_000;
export const MAX_MULTIPLIER = 8;
export const DIM_NAME_RE = /^[A-Za-z_][A-Za-z0-9_]{0,31}$/;
const RESERVED_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

/** 常用参数维度的中文标注 (纯展示, 不影响序列化)。 */
export const DIM_LABELS: Record<string, string> = {
  size: '分辨率',
  duration: '时长(秒)',
  quality: '画质',
  style: '风格',
  ratio: '宽高比',
  resolution: '分辨率',
  steps: '迭代步数',
  n: '数量',
};

/** 按模型类型给出的推荐维度 (新建模型时一键起步, 免得对着空白页发呆)。 */
export const DIM_PRESETS: Record<string, { key: string; values: string[] }[]> = {
  image: [{ key: 'size', values: ['1K', '2K', '4K'] }],
  video: [
    { key: 'size', values: ['720P', '1080P'] },
    { key: 'duration', values: ['5', '10'] },
  ],
  text: [],
  audio: [{ key: 'duration', values: ['30', '60'] }],
  '3d': [{ key: 'quality', values: ['standard', 'high'] }],
};

let uidSeq = 0;
/** 生成 React list 用的稳定 key (不进序列化, 无需全局唯一性保证)。 */
export function nextUid(prefix = 'r'): string {
  uidSeq += 1;
  return `${prefix}${uidSeq}_${Math.random().toString(36).slice(2, 7)}`;
}

export function isSafeDimName(name: string): boolean {
  return DIM_NAME_RE.test(name) && !RESERVED_KEYS.has(name);
}

/** 数量维度默认参数名。 */
export const DEFAULT_MULTIPLIER_KEY = 'n';
/** 未配置定价时的默认基础价 (与后端 DEFAULT_BASE 对齐)。 */
export const DEFAULT_BASE = 10;

/**
 * 反序列化: (pricing_json, params_schema_json) → 表单值。
 *
 * 合并策略: 以两边维度的并集为准 ——
 *   - 只在 params_schema 里有的值 → 档位加价按 0 补齐 (用户能选、不加价)
 *   - 只在 pricing.tiers 里有的值 → 也列出来 (否则管理员看不到已生效的加价, 会误以为丢了)
 * 这样任何历史脏数据打开表单后都能被完整看到并修正, 不会被静默吞掉。
 */
export function toFormValue(
  pricing: PricingRule | null | undefined,
  paramsSchema: unknown,
  modelType?: string,
): PricingFormValue {
  const tiers = (pricing?.tiers ?? {}) as Record<string, Record<string, number>>;
  const schema = normalizeSchemaInput(paramsSchema);
  const multiplierKey = (pricing?.multiplier ?? '').trim();

  const dimKeys: string[] = [];
  for (const k of Object.keys(schema)) {
    if (k !== multiplierKey && isSafeDimName(k) && !dimKeys.includes(k)) dimKeys.push(k);
  }
  for (const k of Object.keys(tiers)) {
    if (k !== multiplierKey && isSafeDimName(k) && !dimKeys.includes(k)) dimKeys.push(k);
  }

  const dims: DimRow[] = dimKeys.map((key) => {
    const table = tiers[key] ?? {};
    const values: string[] = [];
    for (const v of schema[key] ?? []) {
      const s = String(v);
      if (!values.includes(s)) values.push(s);
    }
    for (const v of Object.keys(table)) {
      if (!values.includes(v)) values.push(v);
    }
    return {
      uid: nextUid('d'),
      key,
      tiers: values.map((value) => ({
        uid: nextUid('t'),
        value,
        delta: toFiniteNumber(table[value], 0),
      })),
    };
  });

  const hasMultiplier = !!multiplierKey;
  const multiplierOptions = hasMultiplier
    ? (schema[multiplierKey] ?? []).map(String)
    : [];

  const value: PricingFormValue = {
    base: toFiniteNumber(pricing?.base, DEFAULT_BASE),
    dims,
    multiplierEnabled: hasMultiplier,
    multiplierKey: hasMultiplier ? multiplierKey : DEFAULT_MULTIPLIER_KEY,
    multiplierOptions: multiplierOptions.length ? multiplierOptions : ['1'],
  };

  // 全新模型 (无任何既有配置): 按类型给一套推荐维度作为起点。
  if (!pricing && !dims.length && modelType) {
    value.dims = (DIM_PRESETS[modelType] ?? []).map((p) => ({
      uid: nextUid('d'),
      key: p.key,
      tiers: p.values.map((v) => ({ uid: nextUid('t'), value: v, delta: 0 })),
    }));
  }
  return value;
}

/**
 * 序列化: 表单值 → (pricing_json, params_schema_json)。
 *
 * 空维度、空档位、非法参数名一律丢弃 —— 宁可少存, 也不让残缺结构进入计费真相源。
 * 档位值全为数字时, params_schema 输出数字数组 (与既有种子数据 n:[1,2,4] 口径一致),
 * 而 tiers 的键天然是字符串 (JSON 对象键), 服务端算价时按 String(val) 匹配, 两侧不冲突。
 */
export function toWire(form: PricingFormValue): WireValue {
  const tiers: Record<string, Record<string, number>> = {};
  const schema: Record<string, (string | number)[]> = {};

  for (const dim of form.dims.slice(0, MAX_DIMS)) {
    const key = dim.key.trim();
    if (!isSafeDimName(key)) continue;

    const table: Record<string, number> = {};
    const options: (string | number)[] = [];
    const seen = new Set<string>();
    for (const t of dim.tiers.slice(0, MAX_TIERS_PER_DIM)) {
      const value = String(t.value ?? '').trim();
      if (!value || seen.has(value)) continue;
      seen.add(value);
      table[value] = clamp(Math.floor(toFiniteNumber(t.delta, 0)), -MAX_PRICE, MAX_PRICE);
      options.push(value);
    }
    if (!options.length) continue;
    tiers[key] = table;
    schema[key] = castNumericList(options);
  }

  const mKey = form.multiplierKey.trim();
  const useMultiplier = form.multiplierEnabled && isSafeDimName(mKey) && !tiers[mKey];
  if (useMultiplier) {
    const opts: (string | number)[] = [];
    const seen = new Set<string>();
    for (const raw of form.multiplierOptions.slice(0, MAX_TIERS_PER_DIM)) {
      const v = String(raw ?? '').trim();
      if (!v || seen.has(v)) continue;
      seen.add(v);
      opts.push(v);
    }
    if (opts.length) schema[mKey] = castNumericList(opts);
  }

  const pricing: PricingRule = {
    base: clamp(Math.floor(toFiniteNumber(form.base, DEFAULT_BASE)), 0, MAX_PRICE),
  };
  if (Object.keys(tiers).length) pricing.tiers = tiers;
  if (useMultiplier) pricing.multiplier = mKey;

  return {
    pricing,
    paramsSchema: Object.keys(schema).length ? schema : null,
  };
}

/**
 * 表单校验: 返回人话错误列表 (空数组 = 通过)。
 * 只拦"保存后必然出问题"的情况; 单纯为空的维度在 toWire 里被静默丢弃, 不算错。
 */
export function validateForm(form: PricingFormValue): string[] {
  const errors: string[] = [];
  const base = toFiniteNumber(form.base, NaN);
  if (!Number.isFinite(base) || base < 0) errors.push('基础价必须是不小于 0 的数字');
  else if (base > MAX_PRICE) errors.push(`基础价不能超过 ${MAX_PRICE}`);

  if (form.dims.length > MAX_DIMS) errors.push(`参数维度最多 ${MAX_DIMS} 个`);

  const usedKeys = new Set<string>();
  form.dims.forEach((dim, i) => {
    const key = dim.key.trim();
    if (!key) {
      errors.push(`第 ${i + 1} 个参数维度缺少参数名`);
      return;
    }
    if (!isSafeDimName(key)) {
      errors.push(`参数名 "${key}" 非法：只能用字母、数字、下划线，且不以数字开头`);
      return;
    }
    if (usedKeys.has(key)) errors.push(`参数名 "${key}" 重复`);
    usedKeys.add(key);

    if (dim.tiers.length > MAX_TIERS_PER_DIM) {
      errors.push(`参数 "${key}" 的档位最多 ${MAX_TIERS_PER_DIM} 个`);
    }
    const seen = new Set<string>();
    dim.tiers.forEach((t) => {
      const v = String(t.value ?? '').trim();
      if (!v) {
        errors.push(`参数 "${key}" 存在空的档位值`);
        return;
      }
      if (seen.has(v)) errors.push(`参数 "${key}" 的档位值 "${v}" 重复`);
      seen.add(v);
      if (!Number.isFinite(toFiniteNumber(t.delta, NaN))) {
        errors.push(`参数 "${key}" 档位 "${v}" 的加价必须是数字`);
      }
    });
  });

  if (form.multiplierEnabled) {
    const mKey = form.multiplierKey.trim();
    if (!mKey) errors.push('启用数量倍率时必须填写参数名');
    else if (!isSafeDimName(mKey)) errors.push(`数量参数名 "${mKey}" 非法`);
    else if (usedKeys.has(mKey)) {
      errors.push(`参数名 "${mKey}" 已用作加价维度，不能同时作为数量倍率（一个参数不能既加价又乘倍）`);
    }
    const opts = form.multiplierOptions.map((v) => String(v ?? '').trim()).filter(Boolean);
    if (!opts.length) errors.push('数量倍率至少要有一个可选值');
    for (const o of opts) {
      const n = Number(o);
      if (!Number.isFinite(n) || n < 1) errors.push(`数量可选值 "${o}" 必须是不小于 1 的数字`);
    }
  }
  return errors;
}

/**
 * 试算面板的默认取值: 每个维度取"最贵的那档", 数量取 1。
 * 理由: 管理员最需要一眼看到的是价格天花板 (会不会配出一单几千 Tapies 的黑洞)。
 */
export function defaultPreviewParams(form: PricingFormValue): Record<string, string> {
  const picks: Record<string, string> = {};
  for (const dim of form.dims) {
    const key = dim.key.trim();
    if (!isSafeDimName(key) || !dim.tiers.length) continue;
    let best = dim.tiers[0];
    for (const t of dim.tiers) {
      if (toFiniteNumber(t.delta, 0) > toFiniteNumber(best.delta, 0)) best = t;
    }
    picks[key] = String(best.value ?? '').trim();
  }
  if (form.multiplierEnabled) {
    const mKey = form.multiplierKey.trim();
    const first = form.multiplierOptions.map((v) => String(v ?? '').trim()).filter(Boolean)[0];
    if (isSafeDimName(mKey) && first) picks[mKey] = first;
  }
  return picks;
}

/** 表格里的一行摘要文本 (无 pricing 时给出"默认价"提示)。 */
export function summarizePricing(pricing: PricingRule | null | undefined): string {
  if (!pricing) return `默认 ${DEFAULT_BASE}`;
  const parts = [`基础 ${toFiniteNumber(pricing.base, DEFAULT_BASE)}`];
  for (const [dim, table] of Object.entries(pricing.tiers ?? {})) {
    const items = Object.entries(table ?? {})
      .map(([k, v]) => `${k}${(v as number) >= 0 ? '+' : ''}${v}`)
      .join(' ');
    if (items) parts.push(`${dim}: ${items}`);
  }
  if (pricing.multiplier) parts.push(`×${pricing.multiplier}`);
  return parts.join(' · ');
}

/* ───────────────────────── 内部工具 ───────────────────────── */

function normalizeSchemaInput(input: unknown): Record<string, (string | number)[]> {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return {};
  const out: Record<string, (string | number)[]> = {};
  for (const [k, v] of Object.entries(input as Record<string, unknown>)) {
    if (!isSafeDimName(k)) continue;
    if (!Array.isArray(v)) continue;
    out[k] = v.filter((x) => x !== null && x !== undefined && typeof x !== 'object') as (
      | string
      | number
    )[];
  }
  return out;
}

/** 全是数字则输出数字数组, 否则保持字符串 —— 与既有种子数据的类型口径保持一致。 */
function castNumericList(list: (string | number)[]): (string | number)[] {
  const allNumeric = list.every((v) => String(v).trim() !== '' && Number.isFinite(Number(v)));
  return allNumeric ? list.map((v) => Number(v)) : list.map((v) => String(v));
}

function toFiniteNumber(v: unknown, dflt: number): number {
  if (v === '' || v === null || v === undefined) return dflt;
  const n = Number(v);
  return Number.isFinite(n) ? n : dflt;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}
