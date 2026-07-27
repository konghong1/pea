/* 真机验证：编辑框「相对节点固定、不翻转到上方」。
 * 复现旧逻辑触发条件：把节点平移到视口底部附近（旧代码会因此把编辑框翻到节点上方）。
 * 断言：
 *   1) 编辑框 DOM 位于节点内部（锚定），且 class 恒为 placed-below（不再出现 placed-above）。
 *   2) 编辑框顶部 >= 节点底部（确实在节点正下方，而非翻到上方）。
 *   3) 上方功能条位于节点上方（text 节点）。
 *   4) 0 console error。
 * 运行：node verify_editor_below_node.cjs  （依赖 8088 已部署）
 */
const { chromium } = require('C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules/playwright');
const crypto = require('crypto');

const BASE = 'http://localhost:8088';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.addInitScript("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}");

  let consoleErrors = 0;
  page.on('console', (m) => { if (m.type() === 'error') { consoleErrors++; console.log(`[console:error] ${m.text()}`); } });
  page.on('pageerror', (e) => { consoleErrors++; console.log('[pageerror]', e.message); });

  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(1500);

  await page.getByRole('button', { name: '没有账号？去注册' }).first().click();
  await sleep(300);
  const EMAIL = `ebn_${crypto.randomBytes(4).toString('hex')}@pea.dev`;
  await page.fill('input[placeholder="you@pea.ai"]', EMAIL);
  await page.fill('input[placeholder="至少 8 位"]', 'Password123');
  await page.fill('input[placeholder="可选"]', 'EbnBot');
  await page.locator('form button[type=submit]').click();
  await sleep(4000);

  const token = await page.evaluate(() => localStorage.getItem('pea_token'));
  const cid = await page.evaluate(async () => {
    const t = localStorage.getItem('pea_token');
    const r = await fetch('/canvases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: 'Bearer ' + t } : {}) },
      body: JSON.stringify({ title: 'ebn', scope: 'personal' }),
    });
    return (await r.json()).id;
  });
  await page.evaluate((c) => window.__canvas.getState().openCanvas(c).then(() => window.__ui.getState().setActive('canvas')), cid);
  await page.waitForSelector('.react-flow__viewport', { timeout: 20000 });
  await sleep(1500);

  // 注入一个文本节点（编辑框 + 功能条都会出现）
  await page.evaluate(() => {
    const s = window.__canvas.getState();
    const mk = (id, kind, x, y, extra = {}) => ({ id, type: 'pea', position: { x, y }, data: { kind, label: kind, ...extra } });
    const nTxt = mk('nTxt', 'text', 200, 200, { html: '一只橘猫', meta: {} });
    s.loadGraph([nTxt], [], s.version);
    s.clearSelection();
  });
  await sleep(800);

  let allPass = true;
  const assert = (cond, name, extra) => {
    if (!cond) allPass = false;
    console.log((cond ? 'PASS ' : 'FAIL ') + name, extra !== undefined ? JSON.stringify(extra) : '');
  };

  // ── 选中文本节点 ──
  await page.evaluate(() => { window.__canvas.getState().select('nTxt'); });
  await sleep(1300);

  const measure = () => page.evaluate(() => {
    const node = document.querySelector('.react-flow__node[data-id="nTxt"]');
    const bar = node ? node.querySelector('.node-input-bar') : null;
    const tb = document.querySelector('.text-node-toolbar');
    const nb = node ? node.getBoundingClientRect() : null;
    const bb = bar ? bar.getBoundingClientRect() : null;
    const tbb = tb ? tb.getBoundingClientRect() : null;
    return {
      hasBar: !!bar,
      hasAbove: bar ? bar.classList.contains('placed-above') : null,
      hasBelow: bar ? bar.classList.contains('placed-below') : null,
      barTop: bb ? Math.round(bb.top) : null,
      nodeBottom: nb ? Math.round(nb.bottom) : null,
      nodeTop: nb ? Math.round(nb.top) : null,
      tbBottom: tbb ? Math.round(tbb.bottom) : null,
      vh: window.innerHeight,
    };
  });

  const before = await measure();
  assert(before.hasBar, '编辑框出现在节点内(已锚定)', before);
  assert(before.hasBelow && !before.hasAbove, '默认位置：placed-below 且无 placed-above', { hasBelow: before.hasBelow, hasAbove: before.hasAbove });
  assert(before.barTop != null && before.nodeBottom != null && before.barTop >= before.nodeBottom - 4, '编辑框在节点下方(bar.top >= node.bottom)', { barTop: before.barTop, nodeBottom: before.nodeBottom });

  // ── 关键：把节点平移到视口底部附近，复现旧逻辑「翻到上方」的触发条件 ──
  // 应用为 Figma 风格：普通滚轮 = 平移画布。向下滚，使节点下沉到接近视口底。
  await page.mouse.move(720, 450);
  for (let i = 0; i < 8; i++) { await page.mouse.wheel(0, 120); await sleep(60); }
  await sleep(1200);

  const after = await measure();
  console.log('平移后：nodeTop=%s nodeBottom=%s barTop=%s vh=%s placed-below=%s placed-above=%s',
    after.nodeTop, after.nodeBottom, after.barTop, after.vh, after.hasBelow, after.hasAbove);

  assert(after.hasBelow && !after.hasAbove, '节点贴底时仍 placed-below（不再翻到上方）', { hasBelow: after.hasBelow, hasAbove: after.hasAbove });
  assert(after.barTop != null && after.nodeBottom != null && after.barTop >= after.nodeBottom - 4, '节点贴底时编辑框仍在节点下方(相对固定)', { barTop: after.barTop, nodeBottom: after.nodeBottom });

  // ── 上方功能条应恒在节点上方（相对节点固定）──
  if (after.tbBottom != null && after.nodeTop != null) {
    assert(after.tbBottom <= after.nodeTop + 6, '上方功能条在节点上方(相对固定)', { tbBottom: after.tbBottom, nodeTop: after.nodeTop });
  } else {
    assert(false, '功能条应出现(text 节点)', after);
  }

  console.log('='.repeat(60));
  console.log('CONSOLE ERRORS:', consoleErrors);
  console.log('RESULT:', allPass && consoleErrors === 0 ? 'ALL PASS' : 'HAS FAIL');
  await browser.close();
  process.exit(0);
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(2); });
