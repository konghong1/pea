/* 真机验证：编辑框两个交互 bug
 *  - Bug1：删光文本后旧文本又冒出来（initialHtml 回退 editorText）
 *  - Bug2：删自己输入的字却先删 @ 引用的图片（Backspace 误删 token）
 * 运行：node verify_editor_two_bugs.cjs  （针对 8088，需 localStorage.__peaDevHooks='1'）
 */
const { chromium } = require('C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const BASE = 'http://localhost:8088';
const HERE = __dirname;

const EMAIL = `ed_${crypto.randomBytes(4).toString('hex')}@pea.dev`;
const PW = 'Password123';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function assert(cond, label, extra) {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${extra ? '  ' + JSON.stringify(extra) : ''}`);
  return cond;
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.addInitScript("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}");
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log(`[console:${m.type()}] ${m.text()}`); });
  page.on('pageerror', (e) => console.log('[pageerror]', e.message));

  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(1500);
  await page.getByRole('button', { name: '没有账号？去注册' }).first().click();
  await sleep(300);
  await page.fill('input[placeholder="you@pea.ai"]', EMAIL);
  await page.fill('input[placeholder="至少 8 位"]', PW);
  await page.fill('input[placeholder="可选"]', 'EdBot');
  await page.locator('form button[type=submit]').click();
  await sleep(4000);

  const cid = await page.evaluate(async () => {
    const token = localStorage.getItem('pea_token');
    const r = await fetch('/canvases', { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: JSON.stringify({ title: 'ed', scope: 'personal' }) });
    return (await r.json()).id;
  });
  await page.evaluate((c) => window.__canvas.getState().openCanvas(c).then(() => window.__ui.getState().setActive('canvas')), cid);
  await page.waitForSelector('.react-flow__viewport', { timeout: 20000 });
  await sleep(1500);

  const editorState = () => page.evaluate(() => {
    const ed = document.querySelector('.node-prompt-editor');
    if (!ed) return null;
    return { html: ed.innerHTML, text: (ed.innerText || '').replace(/\u200B/g, '').trim(), tokenCount: ed.querySelectorAll('[data-pea-ref="1"]').length };
  });

  let allPass = true;

  // ───────────── Bug1：删光文本不应被旧文本顶回 ─────────────
  await page.evaluate(() => {
    const s = window.__canvas.getState();
    const n = { id: 'b1', type: 'pea', position: { x: 150, y: 200 }, data: { kind: 'image', label: 'image', meta: { editorText: '一只橘猫坐在窗台' }, prompt: '', resultUrl: 'https://placehold.co/200x200/1fa2dc/ffffff?text=AI', resultUrls: ['https://placehold.co/200x200/1fa2dc/ffffff?text=AI'] } };
    s.loadGraph([n], [], s.version); s.select('b1');
  });
  await sleep(1500);
  const before1 = await editorState();
  const ed1 = page.locator('.node-prompt-editor');
  await ed1.click();
  await sleep(300);
  await page.keyboard.down('Control'); await page.keyboard.press('KeyA'); await page.keyboard.up('Control');
  await page.keyboard.press('Backspace');
  await sleep(800);
  const after1 = await editorState();
  const bug1fixed = assert(after1 && after1.text === '' && !after1.html.includes('一只橘猫'), 'Bug1 删光文本后不被旧 prompt 顶回', { before: before1?.text, after: after1?.text });
  allPass = allPass && bug1fixed;

  // ───────────── Bug2：删自己输入的字不误删 @ 图片 ─────────────
  await page.evaluate(() => {
    const s = window.__canvas.getState();
    const src = { id: 'src', type: 'pea', position: { x: -200, y: 0 }, data: { kind: 'image', label: 'image', prompt: '源图', resultUrl: 'https://placehold.co/200x200/ff7a45/ffffff?text=SRC', resultUrls: ['https://placehold.co/200x200/ff7a45/ffffff?text=SRC'], meta: {} } };
    const tgt = { id: 'b2', type: 'pea', position: { x: 200, y: 0 }, data: { kind: 'image', label: 'image', meta: {}, prompt: '', resultUrl: 'https://placehold.co/200x200/1fa2dc/ffffff?text=AI', resultUrls: ['https://placehold.co/200x200/1fa2dc/ffffff?text=AI'] } };
    s.loadGraph([src, tgt], [{ source: 'src', target: 'b2' }], s.version); s.select('b2');
  });
  await sleep(1500);
  const ed2 = page.locator('.node-prompt-editor');
  await ed2.click();
  await sleep(300);
  // 输入 @ 触发选择器，回车选中上游节点（插入 token）
  await page.keyboard.type('@');
  await sleep(600);
  await page.keyboard.press('Enter');
  await sleep(800);
  const afterInsert = await editorState();
  // 在 token 后面输入自己的字
  await page.keyboard.type('abc');
  await sleep(500);
  const afterType = await editorState();
  // 删除自己输入的 abc（3 次退格）
  await page.keyboard.press('Backspace');
  await page.keyboard.press('Backspace');
  await page.keyboard.press('Backspace');
  await sleep(600);
  const afterDel = await editorState();
  const bug2fixed = assert(afterDel && afterDel.tokenCount === 1 && afterDel.text === '', 'Bug2 删自己的字后 @ 图片 token 仍保留', { afterInsert: afterInsert?.tokenCount, afterType: afterType?.text, afterDel });
  allPass = allPass && bug2fixed;

  // 边界检查：在 token 左缘继续退格仍应能删掉 @ 图片（确认没改过头、把 token 锁死）
  await page.keyboard.press('Backspace');
  await page.keyboard.press('Backspace');
  await sleep(500);
  const afterEdge = await editorState();
  const edgeOk = assert(afterEdge && afterEdge.tokenCount === 0, 'Bug2 边界：在 token 左缘退格可删掉 @ 图片（未改过头）', { afterEdge });
  allPass = allPass && edgeOk;

  console.log('='.repeat(60));
  console.log('RESULT:', allPass ? 'ALL PASS' : 'HAS FAIL');
  await browser.close();
  process.exit(0);
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(2); });
