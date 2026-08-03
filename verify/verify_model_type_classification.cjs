/**
 * 回归验证: suggestModelType 模型能力分类
 *
 * 背景 —— 修复前存在三层缺陷:
 *   1. 权威字段 raw.domain (火山方舟 /api/v3/models 返回) 完全没被读取,
 *      导致 127 个模型里 96 个带权威声明的白白降级到关键字猜测。
 *   2. IMAGE_HINTS 混入裸厂商名 'doubao' —— 而 doubao 是火山全谱系品牌
 *      (文本/图像/视频/向量/3D 全叫 doubao-*), 一命中就把 99 个模型判成 image。
 *   3. 泛词 'art' 命中 doubao-sm[art]-router; 裸 'wan' 会误伤图像模型 wanx。
 *
 * 本脚本**直接从 TS 源码抽取新版实现**(而非重写一遍), 避免"验证代码与被验证
 * 代码各写各的"导致的验证失真; OLD 版按修复前原样内联作为历史基线。
 *
 * 断言:
 *   A. 生产库 ai_models 里已人工确认的 10 条分类, 新逻辑必须完全一致 (零破坏)。
 *   B. Agnes 真实 7 个模型, 新旧结果必须完全一致 (零破坏)。
 *   C. 火山 127 个模型, 新结果必须与权威 domain 字段推导的期望值完全一致。
 *
 * 用法: node verify/verify_model_type_classification.cjs
 * 依赖数据(gitignore, 需先拉取): verify/_agnes_models.json, verify/_volc_models.json
 */
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const TS_SRC = path.join(
  ROOT, 'pea-server', 'services', 'bff', 'src', 'modules', 'providers', 'providers.service.ts',
);

// ── 从 TS 源码抽取新版实现 ─────────────────────────────────────────
function loadNewImpl() {
  const src = fs.readFileSync(TS_SRC, 'utf8');
  const start = src.indexOf('const IMAGE_HINTS');
  if (start < 0) throw new Error('未找到 IMAGE_HINTS, TS 源码结构可能已变');
  const endMark = "  return 'text';\n}";
  const end = src.indexOf(endMark, start);
  if (end < 0) throw new Error('未找到 suggestModelType 结尾, TS 源码结构可能已变');

  let snippet = src.slice(start, end + endMark.length);
  // 1) 去掉 export 关键字
  snippet = snippet.replace(/export\s+function\s+suggestModelType/, 'function suggestModelType');
  // 2) 去掉签名上的 TS 类型注解 (参数类型 + 返回类型), 仅保留参数名,
  //    用泛型写法避免以后改了参数名/返回类型导致正则失配。
  snippet = snippet.replace(
    /function suggestModelType\(([^)]*)\)\s*:[^{]+\{/,
    (_m, params) => {
      const names = params
        .split(',')
        .map((p) => p.split(':')[0].replace(/\?/g, '').trim())
        .filter(Boolean);
      return `function suggestModelType(${names.join(', ')}) {`;
    },
  );
  // 3) 兜底: 任何残留的 RemoteModelType 一律替换, 防止 new Function 因类型注解报语法错
  snippet = snippet.split('RemoteModelType').join('string');
  if (snippet.includes('RemoteModelType')) throw new Error('TS 类型未清理干净 (snippet 见下)\n' + snippet);
  // eslint-disable-next-line no-new-func
  return new Function(`${snippet}\n; return suggestModelType;`)();
}

// ── 修复前的原始实现 (历史基线, 请勿"顺手优化") ──────────────────
const OLD_IMAGE = ['dall-e', 'dalle', 'image', 'imagen', 'stable-diffusion', 'sdxl', 'flux',
  'cogview', 'niji', 'illustrious', 'pony', 'draw', 'paint', 'cartoon', 'art', 'vision',
  'gpt-image', 'gemini', 'midjourney', 'wanx', 'tongyi', 'doubao', 'jiimagine'];
const OLD_VIDEO = ['sora', 'video', 'kling', 'cogvideo', 'runway', 'pika', 'luma', 'veo', 'wan',
  'seedance', 'digo', 'hunyuan-video', 'doubao-video', 'kami', 'mochi',
  'minimax-h', 'hailuo', 't2v-', 'i2v-', 's2v-'];
const OLD_EMBED = ['embedding', 'bge', 'text-embedding', 'e5-', 'gte-', 'm3e', 'bce',
  'jina-embed', 'voyage', 'cohere-embed', 'embed'];
const OLD_AUDIO = ['tts', 'whisper', 'speech', 'audio', 'voice', 'music', 'suno', 'udio',
  'cosyvoice', 'chattts', 'bark', 'fishaudio'];

function oldSuggest(modelId, raw) {
  const lower = (modelId || '').toLowerCase();
  if (raw && typeof raw === 'object') {
    const explicit = raw.type || raw.category || raw.model_type || raw.task;
    if (typeof explicit === 'string' && explicit.toLowerCase() === 'model') {
      // 无信息量
    } else if (typeof explicit === 'string') {
      const e = explicit.toLowerCase();
      if (/(image|img|draw|paint)/.test(e)) return 'image';
      if (/(video|movie|film)/.test(e)) return 'video';
      if (/(embed)/.test(e)) return 'embedding';
      if (/(audio|speech|tts|voice|music|sound)/.test(e)) return 'audio';
      if (/(text|chat|llm|language)/.test(e)) return 'text';
    }
    const caps = raw.capabilities || raw.modality || raw.modalities
      || raw.input_modalities || raw.output_modalities || (raw.architecture || {}).modality;
    const capStr = Array.isArray(caps) ? caps.join(',') : caps ? String(caps) : '';
    if (capStr) {
      const c = capStr.toLowerCase();
      if (/(image|img)/.test(c)) return 'image';
      if (/(video|movie|film)/.test(c)) return 'video';
      if (/(embed)/.test(c)) return 'embedding';
      if (/(audio|speech|voice|music|sound)/.test(c)) return 'audio';
    }
  }
  if (OLD_IMAGE.some((k) => lower.includes(k))) return 'image';
  if (OLD_VIDEO.some((k) => lower.includes(k))) return 'video';
  if (OLD_EMBED.some((k) => lower.includes(k))) return 'embedding';
  if (OLD_AUDIO.some((k) => lower.includes(k))) return 'audio';
  return 'text';
}

// ── 权威 domain -> 期望类型 ────────────────────────────────────────
function expectedFromVolc(m) {
  const d = m.domain || '';
  if (d === 'ImageGeneration') return 'image';
  if (d === 'VideoGeneration') return 'video';
  if (d === 'Embedding') return 'embedding';
  if (d === 'LLM' || d === 'VLM' || d === 'Router') return 'text';
  // 3DGeneration: 本系统不支持 3D 生成, 不扩展 RemoteModelType, 由 text 兜底。
  if (d === '3DGeneration') return 'text';
  // domain 为空 —— 只能靠 id 关键字, 这里按人工核对结论给期望值。
  const id = m.id.toLowerCase();
  if (id.includes('wan2-')) return 'video';       // 通义万相视频 t2v/i2v/flf2v
  if (id.includes('embedding')) return 'embedding';
  return 'text';
}

// ── 断言执行 ───────────────────────────────────────────────────────
const newSuggest = loadNewImpl();
let failed = 0;
const line = (s) => console.log(s);

function readJson(f) {
  const p = path.join(__dirname, f);
  if (!fs.existsSync(p)) {
    line(`  [SKIP] 缺少数据文件 ${f} (需先拉取模型列表)`);
    return null;
  }
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

// A. 生产库已确认分类 (零破坏)
line('=== A. 生产库 ai_models 已确认分类 (必须零破坏) ===');
const PROD = [
  ['agnes-2.0-flash', 'text'], ['agnes-2.5-pro-alpha', 'text'],
  ['agnes-image-2.0-flash', 'image'], ['agnes-image-2.1-flash', 'image'],
  ['agnes-video-v2.0', 'video'],
  ['image-01', 'image'], ['MiniMax-H3', 'video'], ['MiniMax-Hailuo-02', 'video'],
  ['MiniMax-M2', 'text'], ['MiniMax-M2.5', 'text'],
];
for (const [id, want] of PROD) {
  const got = newSuggest(id, undefined);
  const ok = got === want;
  if (!ok) failed++;
  line(`  ${ok ? 'OK  ' : 'FAIL'} ${id.padEnd(24)} want=${want.padEnd(9)} got=${got}`);
}

// B. Agnes 真实列表 (新旧一致)
line('');
line('=== B. Agnes 真实模型 (新旧结果必须一致) ===');
const agnes = readJson('_agnes_models.json');
if (agnes) {
  for (const m of agnes.data) {
    const o = oldSuggest(m.id, m);
    const n = newSuggest(m.id, m);
    const ok = o === n;
    if (!ok) failed++;
    line(`  ${ok ? 'OK  ' : 'FAIL'} ${m.id.padEnd(24)} old=${o.padEnd(9)} new=${n}`);
  }
}

// C. 火山 127 个 (必须匹配权威 domain)
line('');
line('=== C. 火山方舟模型 (必须匹配权威 domain) ===');
const volc = readJson('_volc_models.json');
if (volc) {
  const oldCnt = {}; const newCnt = {}; const wantCnt = {};
  const bad = [];
  for (const m of volc.data) {
    const want = expectedFromVolc(m);
    const o = oldSuggest(m.id, m);
    const n = newSuggest(m.id, m);
    oldCnt[o] = (oldCnt[o] || 0) + 1;
    newCnt[n] = (newCnt[n] || 0) + 1;
    wantCnt[want] = (wantCnt[want] || 0) + 1;
    if (n !== want) bad.push(`${m.id} domain=${m.domain || '(empty)'} want=${want} got=${n}`);
  }
  line(`  修复前分布: ${JSON.stringify(oldCnt)}`);
  line(`  修复后分布: ${JSON.stringify(newCnt)}`);
  line(`  权威期望值: ${JSON.stringify(wantCnt)}`);
  if (bad.length) {
    failed += bad.length;
    line(`  FAIL ${bad.length} 条不符:`);
    bad.slice(0, 20).forEach((b) => line(`    - ${b}`));
  } else {
    line(`  OK   全部 ${volc.data.length} 条与权威 domain 一致`);
  }
}

line('');
line(failed === 0 ? 'ALL_PASS' : `HAS_FAILURES (${failed})`);
process.exit(failed === 0 ? 0 : 1);
