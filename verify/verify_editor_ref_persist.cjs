/* 真机验证：@ 引用图片的两个 bug
 *  - Bug A：刷新后 @ 引用的图片丢失（editorText 之前只存纯文本，@ token 被剥离）
 *  - Bug B：发送时生成的参考图 reference_images 不含 @ 引用的图片（导致生成不参考该图）
 * 验证点：
 *   1) 真实 @ 选择器路径（带边）：@ 引用 → 发送 → reference_images 含该图；刷新后 token 仍在。
 *   2) 纯 @ token 路径（无边）：仅 @ 引用、无连接边 → 发送 → reference_images 仍含该图（决定性复现 Bug B）。
 * 运行：node verify_editor_ref_persist.cjs  （针对 8088，需 localStorage.__peaDevHooks='1'）
 */
const { chromium } = require('C:/Users/admin/.workbuddy/binaries/node/workspace/node_modules/playwright');
const crypto = require('crypto');

const BASE = 'http://localhost:8088';
const EMAIL = `erp_${crypto.randomBytes(4).toString('hex')}@pea.dev`;
const PW = 'Password123';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const results = [];
function assert(cond, label, extra) {
  results.push(cond);
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${extra !== undefined ? '  ' + JSON.stringify(extra) : ''}`);
  return cond;
}

const BAG = 'https://placehold.co/220x220/16a34a/ffffff?text=BAG';
const BAG2 = 'https://placehold.co/220x220/db2777/ffffff?text=BAG2';

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.addInitScript("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}");
  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + e.message));

  // ── 注册 + 建画布 + 打开 ──
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(1500);
  await page.getByRole('button', { name: '没有账号？去注册' }).first().click();
  await sleep(300);
  await page.fill('input[placeholder="you@pea.ai"]', EMAIL);
  await page.fill('input[placeholder="至少 8 位"]', PW);
  await page.fill('input[placeholder="可选"]', 'ErpBot');
  await page.locator('form button[type=submit]').click();
  await sleep(4000);

  const cid = await page.evaluate(async () => {
    const token = localStorage.getItem('pea_token');
    const r = await fetch('/canvases', { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: JSON.stringify({ title: 'erp', scope: 'personal' }) });
    return (await r.json()).id;
  });
  await page.evaluate((c) => window.__canvas.getState().openCanvas(c).then(() => window.__ui.getState().setActive('canvas')), cid);
  await page.waitForSelector('.react-flow__viewport', { timeout: 20000 });
  await sleep(1200);

  const editorState = () => page.evaluate(() => {
    const ed = document.querySelector('.node-prompt-editor');
    if (!ed) return null;
    return {
      html: ed.innerHTML,
      tokenCount: ed.querySelectorAll('[data-pea-ref="1"]').length,
      imgSrcs: Array.from(ed.querySelectorAll('img.pea-ref-thumb')).map((i) => i.getAttribute('src')),
    };
  });
  const openCanvasAgain = async () => {
    const id = await page.evaluate(async () => {
      const token = localStorage.getItem('pea_token');
      const r = await fetch('/canvases', { headers: { ...(token ? { Authorization: 'Bearer ' + token } : {}) } });
      const list = await r.json();
      const c = (list.items || list).find((x) => x.title === 'erp');
      return c ? c.id : null;
    });
    await page.evaluate((c) => window.__canvas.getState().openCanvas(c).then(() => window.__ui.getState().setActive('canvas')), id);
    await page.waitForSelector('.react-flow__viewport', { timeout: 20000 });
    await sleep(1200);
  };

  // ════════ 测试 1：真实 @ 选择器路径（带边），刷新后 token 仍在，且生成参考该图 ════════
  await page.evaluate(({ bag }) => {
    const s = window.__canvas.getState();
    const bagNode = { id: 'bag', type: 'pea', position: { x: -260, y: 0 }, data: { kind: 'image', label: 'image', prompt: '包', resultUrl: bag, resultUrls: [bag], meta: {} } };
    const cat = { id: 'cat', type: 'pea', position: { x: 220, y: 0 }, data: { kind: 'image', label: 'image', prompt: '', resultUrl: 'https://placehold.co/200x200/1fa2dc/ffffff?text=CAT', resultUrls: ['https://placehold.co/200x200/1fa2dc/ffffff?text=CAT'], meta: {} } };
    s.loadGraph([bagNode, cat], [{ source: 'bag', target: 'cat' }], s.version);
    s.select('cat');
  }, { bag: BAG });
  await sleep(1400);

  const ed = page.locator('.node-prompt-editor');
  await ed.click();
  await sleep(300);
  await page.keyboard.type('@');
  await sleep(700);
  await page.keyboard.press('Enter'); // 选中唯一上游节点 bag，插入 token
  await sleep(800);
  const afterInsert = await editorState();
  assert(afterInsert && afterInsert.tokenCount === 1, 'T1 @ 选择器插入 token 成功', { tokenCount: afterInsert?.tokenCount });

  await page.keyboard.type('把包放在猫咪身边');
  await sleep(400);
  await page.keyboard.press('Enter'); // 发送（submit）
  await sleep(1800);

  // 发送后：持久化的 genParams.reference_images 应包含 bag URL
  const meta1 = await page.evaluate(() => {
    const n = window.__canvas.getState().nodes.find((x) => x.id === 'cat');
    return { ref: n?.data?.meta?.genParams?.reference_images || [], editorText: n?.data?.meta?.editorText || '' };
  });
  assert(meta1.ref.includes(BAG), 'T1 发送时 reference_images 含 @ 引用的包（Bug B 修复）', { ref: meta1.ref });
  assert(meta1.editorText.includes('data-pea-ref'), 'T1 发送的 editorText 仍含 @ token（持久化完整 HTML）', { hasToken: meta1.editorText.includes('data-pea-ref') });

  // 等待自动保存落库后刷新
  await sleep(2200);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await sleep(1500);
  await openCanvasAgain();
  await sleep(1400);
  await page.evaluate(() => window.__canvas.getState().select('cat'));
  await sleep(1400);
  const afterReload = await editorState();
  assert(afterReload && afterReload.tokenCount === 1, 'T1 刷新后 @ token 仍在编辑框（Bug A 修复）', { tokenCount: afterReload?.tokenCount });
  assert(afterReload && afterReload.imgSrcs.some((s) => s && s.includes('BAG')), 'T1 刷新后 token 缩略图指向包图', { imgSrcs: afterReload?.imgSrcs });
  const meta1r = await page.evaluate(() => {
    const n = window.__canvas.getState().nodes.find((x) => x.id === 'cat');
    return { ref: n?.data?.meta?.genParams?.reference_images || [], editorText: n?.data?.meta?.editorText || '' };
  });
  assert(meta1r.ref.includes(BAG) && meta1r.editorText.includes('data-pea-ref'), 'T1 刷新后 meta 仍含 reference_images 与 @ token', { ref: meta1r.ref, hasToken: meta1r.editorText.includes('data-pea-ref') });

  // ════════ 测试 2：纯 @ token 路径（无边）—— 决定性复现 Bug B ════════
  await page.evaluate(({ bag2 }) => {
    const s = window.__canvas.getState();
    const bagNode = { id: 'bag2', type: 'pea', position: { x: -260, y: 200 }, data: { kind: 'image', label: 'image', prompt: '包2', resultUrl: bag2, resultUrls: [bag2], meta: {} } };
    const cat2 = { id: 'cat2', type: 'pea', position: { x: 220, y: 200 }, data: { kind: 'image', label: 'image', prompt: '', resultUrl: 'https://placehold.co/200x200/1fa2dc/ffffff?text=CAT2', resultUrls: ['https://placehold.co/200x200/1fa2dc/ffffff?text=CAT2'], meta: {} } };
    // 注意：bag2 与 cat2 之间不连边 —— @ token 是唯一的引用载体
    s.loadGraph([bagNode, cat2], [], s.version);
    s.select('cat2');
  }, { bag2: BAG2 });
  await sleep(1400);

  // 直接注入 @ token（与 @ 选择器 insertRefToken 产出的 DOM 完全一致），模拟用户 @ 引用 bag2
  await page.evaluate(({ bag2 }) => {
    const ed = document.querySelector('.node-prompt-editor');
    ed.innerHTML = `<span class="pea-ref" contenteditable="false" data-node-id="bag2" data-kind="image" data-pea-ref="1"><span class="pea-ref-inner"><img class="pea-ref-thumb" src="${bag2}"></span></span>把包2放在猫咪身边`;
    ed.dispatchEvent(new Event('input', { bubbles: true }));
  }, { bag2: BAG2 });
  await sleep(600);
  const beforeSend2 = await editorState();
  assert(beforeSend2 && beforeSend2.tokenCount === 1, 'T2 注入 @ token 成功（无边场景）', { tokenCount: beforeSend2?.tokenCount });

  await ed.click();
  await sleep(200);
  await page.keyboard.press('Enter'); // 发送
  await sleep(1800);
  const meta2 = await page.evaluate(() => {
    const n = window.__canvas.getState().nodes.find((x) => x.id === 'cat2');
    return { ref: n?.data?.meta?.genParams?.reference_images || [], editorText: n?.data?.meta?.editorText || '' };
  });
  assert(meta2.ref.includes(BAG2), 'T2 无边场景：发送时 reference_images 仍含 @ 引用的包2（Bug B 决定性修复）', { ref: meta2.ref });

  assert(consoleErrors.length === 0, '无 console error', { errors: consoleErrors.slice(0, 5) });

  console.log('='.repeat(60));
  const allPass = results.every(Boolean);
  console.log('RESULT:', allPass ? 'ALL PASS' : 'HAS FAIL');
  await browser.close();
  process.exit(0);
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(2); });
