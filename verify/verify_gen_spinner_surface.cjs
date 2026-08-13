/* 验证：figma / cinematic 表面下「生成中」spinner 是否可见。
 * 直接在已加载真实 CSS 的页面注入生成中节点 DOM，读取计算色 + 截图。
 * 运行：node verify_gen_spinner_surface.cjs
 */
const { chromium } = require('C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules/playwright');

const BASE = 'http://localhost:8088';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 复刻 TechLoader.tsx 的 SVG 输出
function techLoaderMarkup() {
  const size = 56, stroke = 2;
  const rOuter = (size - stroke) / 2 - 2;
  const rMid = rOuter - 6;
  const rInner = rMid - 6;
  const cx = size / 2, cy = size / 2;
  const c = 2 * Math.PI * rOuter;
  return `
  <div class="tech-loader" style="width:${size}px" role="status">
    <svg class="tech-loader__svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden>
      <circle class="tech-loader__ring tech-loader__ring--outer" cx="${cx}" cy="${cy}" r="${rOuter}" fill="none" stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${c*0.18} ${c*0.12}" opacity="0.55"/>
      <circle class="tech-loader__ring tech-loader__ring--mid" cx="${cx}" cy="${cy}" r="${rMid}" fill="none" stroke="currentColor" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${c*0.1} ${c*0.16}" opacity="0.7"/>
      <circle class="tech-loader__ring tech-loader__ring--arc" cx="${cx}" cy="${cy}" r="${rInner}" fill="none" stroke="currentColor" stroke-width="${stroke+0.5}" stroke-linecap="round" stroke-dasharray="${c*0.28} ${c}"/>
      <circle class="tech-loader__core" cx="${cx}" cy="${cy}" r="${rInner*0.42}" fill="#8b5cf6"/>
    </svg>
    <span class="tech-loader__label">生成中…</span>
  </div>`;
}

function genNodeMarkup(label) {
  return `
  <div class="pea-node pea-node-video pea-node-has-media is-generating" style="position:relative;width:240px;margin:14px;">
    <div class="pea-node-body-card">
      <div class="pea-node-generating" aria-label="生成中">
        ${techLoaderMarkup()}
      </div>
    </div>
    <div style="position:absolute;top:-10px;left:12px;font-size:12px;color:#666;">${label}</div>
  </div>`;
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
  const ctx = await browser.newContext({ viewport: { width: 760, height: 420 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));

  await page.goto(BASE, { waitUntil: 'networkidle' });
  await sleep(1200);

  // 注入测试夹具：figma + cinematic 两个表面各一个生成中节点
  const html = await page.evaluate(({ figmaMk, cineMk }) => {
    const wrap = document.createElement('div');
    wrap.id = '__gen_verify';
    wrap.style.cssText = 'position:fixed;top:20px;left:20px;z-index:99999;display:flex;gap:24px;background:#ddd;padding:16px;';
    wrap.innerHTML = `
      <div data-surface="figma" style="display:flex;flex-direction:column;align-items:center;">
        ${figmaMk}
      </div>
      <div data-surface="cinematic" style="display:flex;flex-direction:column;align-items:center;">
        ${cineMk}
      </div>`;
    document.body.appendChild(wrap);
    return wrap.innerHTML.length;
  }, { figmaMk: genNodeMarkup('figma 表面'), cineMk: genNodeMarkup('cinematic 表面') });

  await sleep(400);

  // 读取计算色
  const result = await page.evaluate(() => {
    const out = {};
    const figF = document.querySelector('[data-surface="figma"] .tech-loader');
    const figC = document.querySelector('[data-surface="figma"] .tech-loader__ring--arc');
    const cinF = document.querySelector('[data-surface="cinematic"] .tech-loader');
    const cinC = document.querySelector('[data-surface="cinematic"] .tech-loader__ring--arc');
    const cs = (el) => el ? getComputedStyle(el) : null;
    out.figma_techloader_color = cs(figF)?.color;
    out.figma_ring_stroke = cs(figC)?.stroke;
    out.figma_panel_bg = cs(document.querySelector('[data-surface="figma"] .pea-node-generating'))?.backgroundColor;
    out.cinematic_techloader_color = cs(cinF)?.color;
    out.cinematic_ring_stroke = cs(cinC)?.stroke;
    out.cinematic_panel_bg = cs(document.querySelector('[data-surface="cinematic"] .pea-node-generating'))?.backgroundColor;
    return out;
  });

  console.log('=== 计算样式结果 ===');
  console.log(JSON.stringify(result, null, 2));

  await page.screenshot({ path: 'D:/workspace/pea/verify/verify_gen_spinner_surface.png', fullPage: false });
  console.log('截图已保存: verify_gen_spinner_surface.png');
  if (errors.length) console.log('PAGE ERRORS:', errors);

  await browser.close();
})().catch((e) => { console.error('SCRIPT FAILED:', e); process.exit(1); });
