/* 真机验证：编辑框/功能条「锚定节点 + 缩放不变形」。
 * 1) 编辑框是节点 DOM 的子元素（不再是 fixed 浮层）-> 随节点平移无缝贴合。
 * 2) 放大画布时：节点变大，但编辑框/功能条屏幕尺寸恒定（counter-scale 1/zoom）。
 * 3) 顶部功能条样式与编辑框一致（圆角卡片、统一玻璃质感），且缩放不变形。
 * 运行：node verify_editor_anchor_zoom.cjs
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

  // 注册并登录
  await page.getByRole('button', { name: '没有账号？去注册' }).first().click();
  await sleep(300);
  const EMAIL = `anch_${crypto.randomBytes(4).toString('hex')}@pea.dev`;
  await page.fill('input[placeholder="you@pea.ai"]', EMAIL);
  await page.fill('input[placeholder="至少 8 位"]', 'Password123');
  await page.fill('input[placeholder="可选"]', 'AnchBot');
  await page.locator('form button[type=submit]').click();
  await sleep(4000);

  const token = await page.evaluate(() => localStorage.getItem('pea_token'));
  const cid = await page.evaluate(async () => {
    const t = localStorage.getItem('pea_token');
    const r = await fetch('/canvases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: 'Bearer ' + t } : {}) },
      body: JSON.stringify({ title: 'anch', scope: 'personal' }),
    });
    return (await r.json()).id;
  });
  await page.evaluate((c) => window.__canvas.getState().openCanvas(c).then(() => window.__ui.getState().setActive('canvas')), cid);
  await page.waitForSelector('.react-flow__viewport', { timeout: 20000 });
  await sleep(1500);

  // 注入两个节点：文本节点 + AI 图片节点
  await page.evaluate(() => {
    const s = window.__canvas.getState();
    const mk = (id, kind, x, y, extra = {}) => ({ id, type: 'pea', position: { x, y }, data: { kind, label: kind, ...extra } });
    const nTxt = mk('nTxt', 'text', 200, 200, { html: '一只橘猫', meta: {} });
    const nImg = mk('nImg', 'image', 700, 200, {
      resultUrl: 'https://placehold.co/220x220/1fa2dc/fff?text=AI',
      resultUrls: ['https://placehold.co/220x220/1fa2dc/fff?text=AI'],
      prompt: '一只猫', meta: {},
    });
    s.loadGraph([nTxt, nImg], [], s.version);
    s.clearSelection();
  });
  await sleep(800);

  let allPass = true;
  const assert = (cond, name, extra) => {
    if (!cond) allPass = false;
    console.log((cond ? 'PASS ' : 'FAIL ') + name, extra !== undefined ? JSON.stringify(extra) : '');
  };

  // ── 选中文本节点：编辑框应作为节点子元素出现（锚定） ──
  await page.evaluate(() => { window.__canvas.getState().select('nTxt'); });
  await sleep(1300);
  const r1 = await page.evaluate(() => {
    const node = document.querySelector('.react-flow__node[data-id="nTxt"]');
    const bar = node ? node.querySelector('.node-input-bar') : null;
    const nb = node ? node.getBoundingClientRect() : null;
    const bb = bar ? bar.getBoundingClientRect() : null;
    return {
      anchoredInsideNode: !!bar,
      invZoom: getComputedStyle(document.documentElement).getPropertyValue('--pea-inv-zoom').trim(),
      barW: bb ? Math.round(bb.width) : null,
      barCenterX: bb ? Math.round(bb.left + bb.width / 2) : null,
      nodeCenterX: nb ? Math.round(nb.left + nb.width / 2) : null,
    };
  });
  assert(r1.anchoredInsideNode, '编辑框锚定在节点 DOM 内部(不再是 fixed 浮层)', r1);
  assert(Math.abs(parseFloat(r1.invZoom) - 1) < 0.01, '初始 --pea-inv-zoom ≈ 1 (zoom=1)', r1.invZoom);
  assert(r1.barCenterX != null && r1.nodeCenterX != null && Math.abs(r1.barCenterX - r1.nodeCenterX) < 30, '编辑框水平居中于节点(相对固定)', { barCenterX: r1.barCenterX, nodeCenterX: r1.nodeCenterX });
  const baseBarW = r1.barW;

  // ── 放大画布：节点变大，编辑框屏幕尺寸不变 ──
  // 本应用 Figma 风格：panOnScroll + zoomOnDoubleClick=false，缩放走 Ctrl+滚轮
  await page.mouse.move(720, 450);
  await page.keyboard.down('Control');
  await page.mouse.wheel(0, -600);
  await page.mouse.wheel(0, -600);
  await page.keyboard.up('Control');
  await sleep(1200);
  const r2 = await page.evaluate(() => {
    const node = document.querySelector('.react-flow__node[data-id="nTxt"]');
    const card = node.querySelector('.pea-node-body-card');
    const bar = node.querySelector('.node-input-bar');
    return {
      invZoom: getComputedStyle(document.documentElement).getPropertyValue('--pea-inv-zoom').trim(),
      cardW: Math.round(card.getBoundingClientRect().width),
      barW: Math.round(bar.getBoundingClientRect().width),
      barCenterX: Math.round(bar.getBoundingClientRect().left + bar.getBoundingClientRect().width / 2),
      nodeCenterX: Math.round(node.getBoundingClientRect().left + node.getBoundingClientRect().width / 2),
    };
  });
  const z = 1 / parseFloat(r2.invZoom);
  console.log('放大后 zoom ≈', z.toFixed(2));
  assert(parseFloat(r2.invZoom) < 0.9, '放大后 --pea-inv-zoom 已更新(<0.9)', r2.invZoom);
  assert(r2.cardW > baseBarW * 1.3, '节点卡片随缩放变大(card 明显变宽)', { cardW: r2.cardW, baseBarW });
  assert(Math.abs(r2.barW - baseBarW) <= Math.max(8, baseBarW * 0.04), '编辑框屏幕尺寸恒定(不随缩放变形)', { barW: r2.barW, baseBarW });
  assert(Math.abs(r2.barCenterX - r2.nodeCenterX) < 30, '放大后编辑框仍水平居中于节点(贴合)', { barCenterX: r2.barCenterX, nodeCenterX: r2.nodeCenterX });

  // ── 顶部功能条：选中图片节点，检查 counter-scale + 样式与编辑框一致 ──
  await page.evaluate(() => { window.__canvas.getState().select('nImg'); });
  await sleep(1300);
  const r3 = await page.evaluate(() => {
    const node = document.querySelector('.react-flow__node[data-id="nImg"]');
    const tb = node ? node.querySelector('.pea-node-result-toolbar') : null;
    if (!tb) return { present: false };
    const cs = getComputedStyle(tb);
    // 解析 transform 矩阵的 scaleX(a)，应为 counter-scale 因子（≈ 1/zoom）
    const m = cs.transform.match(/matrix\(([^,]+)/);
    const a = m ? parseFloat(m[1]) : 1;
    return {
      present: true,
      scaleX: a,
      borderRadius: cs.borderRadius,
      bg: cs.backgroundColor,
      tbW: Math.round(tb.getBoundingClientRect().width),
    };
  });
  const invZoom2 = parseFloat(r2.invZoom);
  assert(r3.present && r3.scaleX < 0.95, '顶部功能条应用 counter-scale(缩放不变形)', { scaleX: r3.scaleX });
  assert(Math.abs(r3.scaleX - invZoom2) < 0.05, '功能条 scale ≈ 1/zoom(与编辑框同步抵消)', { scaleX: r3.scaleX, invZoom: invZoom2 });
  assert(Math.abs(r3.tbW - 340) <= 30, '功能条屏幕尺寸恒定(不随缩放变形)', { tbW: r3.tbW });
  assert(r3.borderRadius === '14px', '顶部功能条圆角=14px，与编辑框卡片一致(不再是 999px 药丸)', r3.borderRadius);
  assert(/28,\s*28,\s*34/.test(r3.bg || ''), '顶部功能条玻璃底色与编辑框一致(rgba(28,28,34))', r3.bg);

  console.log('='.repeat(60));
  console.log('CONSOLE ERRORS:', consoleErrors);
  console.log('RESULT:', allPass && consoleErrors === 0 ? 'ALL PASS' : 'HAS FAIL');
  await browser.close();
  process.exit(0);
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(2); });
