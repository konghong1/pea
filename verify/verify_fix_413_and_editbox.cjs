/* 真机验证：修复前/后 复现 413 与 编辑框不弹。
 * 注意：page.evaluate 必须传【真实函数】，不能传字符串函数表达式（否则不执行）。
 * 运行：node verify_fix_413_and_editbox.cjs
 */
const { chromium } = require('C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const BASE = 'http://localhost:8088';
const HERE = __dirname;
const LARGE = path.join(HERE, '_large_6mb.bin');
if (!fs.existsSync(LARGE)) fs.writeFileSync(LARGE, crypto.randomBytes(6 * 1024 * 1024));

const EMAIL = `fix_${crypto.randomBytes(4).toString('hex')}@pea.dev`;
const PW = 'Password123';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.addInitScript("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}");

  const uploadStatuses = [];
  page.on('response', (r) => { if (r.url().includes('/files/upload')) uploadStatuses.push([r.status(), r.url()]); });
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log(`[console:${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => console.log('[pageerror]', e));

  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(1500);

  // 注册并登录
  await page.getByRole('button', { name: '没有账号？去注册' }).first().click();
  await sleep(300);
  await page.fill('input[placeholder="you@pea.ai"]', EMAIL);
  await page.fill('input[placeholder="至少 8 位"]', PW);
  await page.fill('input[placeholder="可选"]', 'FixBot');
  await page.locator('form button[type=submit]').click();
  await sleep(4000);

  const token = await page.evaluate(() => localStorage.getItem('pea_token'));
  console.log('TOKEN:', token ? token.slice(0, 12) + '...' : 'NONE');
  const cid = await page.evaluate(async () => {
    const token = localStorage.getItem('pea_token');
    const r = await fetch('/canvases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) },
      body: JSON.stringify({ title: 'fix', scope: 'personal' }),
    });
    const j = await r.json();
    return j.id;
  });
  console.log('CANVAS ID:', cid);
  await page.evaluate((cid) => window.__canvas.getState().openCanvas(cid).then(() => window.__ui.getState().setActive('canvas')), cid);
  await page.waitForSelector('.react-flow__viewport', { timeout: 20000 });
  await sleep(1500);

  // ── 测试 A: 上传 6MB 大图（修复前 nginx 默认 1m -> 413）──
  await page.evaluate(() => {
    const store = window.__canvas.getState();
    const mk = (id, kind, x, y, extra = {}) => ({ id, type: 'pea', position: { x, y }, data: { kind, label: kind, ...extra } });
    const nUp = mk('nUp', 'image', 150, 200, { prompt: '', meta: {} });
    store.loadGraph([nUp], [], store.version);
    store.select('nUp');
  });
  await sleep(1500);
  const inp = page.locator('.react-flow__node[data-id="nUp"] input[type=file]');
  uploadStatuses.length = 0;
  try { await inp.setInputFiles(LARGE, { timeout: 20000 }); } catch (e) { console.log('[warn] setInputFiles:', e.message); }
  await sleep(4000);
  const upState = await page.evaluate(() => {
    const n = window.__canvas.getState().nodes.find((x) => x.id === 'nUp');
    return { fileKey: n?.data?.fileKey || null, url: n?.data?.url || null };
  });
  // BFF 成功上传返回 201 Created（非 200），故以 2xx 为准。
  const passA = uploadStatuses.some(([s]) => s >= 200 && s < 300) && Boolean(upState.fileKey);
  console.log('='.repeat(60));
  console.log('TEST A 上传 6MB 大图:', passA ? 'PASS' : 'FAIL');
  console.log('   /files/upload 响应:', JSON.stringify(uploadStatuses));
  console.log('   节点结果:', JSON.stringify(upState));

  // ── 测试 B: 点击 AI 生成的图片 -> 编辑框弹出（且必须在视口内可见）──
  async function testEditBox(nodeId, x, y, label) {
    await page.evaluate(({ nodeId, x, y }) => {
      const store = window.__canvas.getState();
      const mk = (id, kind, x, y, extra = {}) => ({ id, type: 'pea', position: { x, y }, data: { kind, label: kind, ...extra } });
      const n = mk(nodeId, 'image', x, y, {
        resultUrl: 'https://placehold.co/200x200/1fa2dc/ffffff?text=AI',
        resultUrls: ['https://placehold.co/200x200/1fa2dc/ffffff?text=AI'],
        prompt: '一只猫', meta: {},
      });
      store.loadGraph([n], [], store.version);
      store.clearSelection();
    }, { nodeId, x, y });
    await sleep(1200);
    const img = page.locator(`.react-flow__node[data-id="${nodeId}"] img`);
    const ib = await img.boundingBox();
    await page.mouse.click(ib.x + ib.width / 2, ib.y + ib.height / 2);
    await sleep(2000);
    const res = await page.evaluate((nodeId) => {
      const s = window.__canvas.getState();
      const bar = document.querySelector('.node-input-bar');
      const b = bar ? bar.getBoundingClientRect() : null;
      return {
        selectedId: s.selectedId,
        hasInputBar: !!bar,
        // 是否在视口内可见（vx=1440, vy=900）
        visible: b ? (b.top >= 0 && b.bottom <= 900 && b.left >= 0 && b.right <= 1440) : false,
        box: b ? { top: Math.round(b.top), bottom: Math.round(b.bottom), left: Math.round(b.left), right: Math.round(b.right) } : null,
      };
    }, nodeId);
    const pass = res.selectedId === nodeId && res.hasInputBar && res.visible;
    console.log(`TEST B [${label}] 点击生成图->编辑框:`, pass ? 'PASS' : 'FAIL', JSON.stringify(res));
    return pass;
  }

  const b1 = await testEditBox('nLow', 150, 450, '偏低节点(验证翻转到上方)');
  const b2 = await testEditBox('nHigh', 150, 150, '偏高节点(验证不误翻转)');
  const passB = b1 && b2;
  console.log('='.repeat(60));
  console.log('RESULT:', passA && passB ? 'ALL PASS' : 'HAS FAIL');

  await browser.close();
  process.exit(0);
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(2); });
