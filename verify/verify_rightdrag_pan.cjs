/* 真机验证：画布「右键拖拽平移」。
 * 验证点：
 *  1) 右键在空白画布按下并拖动 -> 视口 translate 跟随指针位移（平移生效）。
 *  2) 右键单击（不拖动）-> 仍弹出画布右键菜单（打开节点库/适配视图），拖拽与菜单互不冲突。
 *  3) 左键拖拽仍为框选（selectionOnDrag 未被破坏），不会平移。
 *  4) 平移过程中不应弹出右键菜单（contextmenu 被抑制）。
 * 运行：node verify_rightdrag_pan.cjs
 */
const { chromium } = require('C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules/playwright');
const crypto = require('crypto');

const BASE = 'http://localhost:8088';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const readViewport = () => {
  const v = document.querySelector('.react-flow__viewport');
  if (!v) return null;
  const m = new DOMMatrixReadOnly(getComputedStyle(v).transform);
  return { x: m.e, y: m.f, k: m.a };
};

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
  const EMAIL = `rpan_${crypto.randomBytes(4).toString('hex')}@pea.dev`;
  await page.fill('input[placeholder="you@pea.ai"]', EMAIL);
  await page.fill('input[placeholder="至少 8 位"]', 'Password123');
  await page.fill('input[placeholder="可选"]', 'RpanBot');
  await page.locator('form button[type=submit]').click();
  await sleep(4000);

  const cid = await page.evaluate(async () => {
    const t = localStorage.getItem('pea_token');
    const r = await fetch('/canvases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: 'Bearer ' + t } : {}) },
      body: JSON.stringify({ title: 'rpan', scope: 'personal' }),
    });
    return (await r.json()).id;
  });
  await page.evaluate((c) => window.__canvas.getState().openCanvas(c).then(() => window.__ui.getState().setActive('canvas')), cid);
  await page.waitForSelector('.react-flow__viewport', { timeout: 20000 });
  await sleep(1500);

  // 清空为纯空白画布，确保拖拽起点落在 pane 上
  await page.evaluate(() => { const s = window.__canvas.getState(); s.loadGraph([], [], s.version); s.clearSelection(); });
  await sleep(600);

  let allPass = true;
  const assert = (cond, name, extra) => {
    if (!cond) allPass = false;
    console.log((cond ? 'PASS ' : 'FAIL ') + name, extra !== undefined ? JSON.stringify(extra) : '');
  };

  const cx = 720, cy = 450;

  // ── 1) 右键单击（不拖动）应弹出菜单 ──
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: 'right' });
  await page.mouse.up({ button: 'right' });
  await sleep(300);
  const menuVisible = await page.evaluate(() => {
    const backdrop = document.querySelector('.fixed.inset-0');
    const menuText = document.body.innerText;
    return { hasBackdrop: !!backdrop, hasLib: menuText.includes('打开节点库') };
  });
  assert(menuVisible.hasBackdrop && menuVisible.hasLib, '右键单击弹出画布菜单(打开节点库)', menuVisible);
  // 关闭菜单：点背景
  await page.click('.fixed.inset-0', { timeout: 3000 }).catch(() => {});
  await sleep(300);

  // ── 2) 右键拖拽应平移画布 ──
  const before = await page.evaluate(readViewport);
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: 'right' });
  await page.mouse.move(cx + 140, cy + 90, { steps: 10 });
  await page.mouse.up({ button: 'right' });
  await sleep(300);
  const after = await page.evaluate(readViewport);
  const dx = after.x - before.x;
  const dy = after.y - before.y;
  assert(Math.abs(dx - 140) <= 25, '右键拖拽后视口 X 平移≈140', { dx: Math.round(dx) });
  assert(Math.abs(dy - 90) <= 25, '右键拖拽后视口 Y 平移≈90', { dy: Math.round(dy) });
  const noMenuAfterDrag = await page.evaluate(() => !document.querySelector('.fixed.inset-0'));
  assert(noMenuAfterDrag, '右键拖拽后未误弹菜单(contextmenu 被抑制)', { noMenuAfterDrag });

  // ── 3) 左键拖拽仍是框选，不应平移 ──
  const beforeSel = await page.evaluate(readViewport);
  await page.mouse.move(cx, cy);
  await page.mouse.down({ button: 'left' });
  await page.mouse.move(cx + 120, cy + 80, { steps: 8 });
  const selectionAppeared = await page.evaluate(() => !!document.querySelector('.react-flow__selection'));
  await page.mouse.up({ button: 'left' });
  await sleep(200);
  const afterSel = await page.evaluate(readViewport);
  assert(selectionAppeared, '左键拖拽出现框选矩形(selectionOnDrag 正常)', { selectionAppeared });
  assert(Math.abs((afterSel.x - beforeSel.x)) < 3 && Math.abs((afterSel.y - beforeSel.y)) < 3, '左键拖拽不平移画布', { ddx: Math.round(afterSel.x - beforeSel.x), ddy: Math.round(afterSel.y - beforeSel.y) });

  console.log('='.repeat(60));
  console.log('CONSOLE ERRORS:', consoleErrors);
  console.log('RESULT:', allPass && consoleErrors === 0 ? 'ALL PASS' : 'HAS FAIL');
  await browser.close();
  process.exit(0);
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(2); });
