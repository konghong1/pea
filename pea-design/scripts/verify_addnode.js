const { chromium } = require('playwright');
const path = 'file://' + require('path').resolve('pea-canvas-v7.html');

(async () => {
  const errors = [];
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  await page.goto(path);
  await page.waitForTimeout(400);
  await page.evaluate(() => switchPage('canvas'));
  await page.waitForTimeout(300);

  const r = {};

  // initial state
  r.initNodes = await page.evaluate(() => document.querySelectorAll('.rf-node').length);
  r.hintInitDisplay = await page.evaluate(() => {
    const h = document.getElementById('canvasHint');
    return h ? getComputedStyle(h).display : 'MISSING';
  });

  // 1) CLICK add (➕ button) -> palette
  await page.click('#addBtn');
  await page.waitForTimeout(200);
  r.clickPalette = await page.evaluate(() => {
    const p = document.querySelector('.add-pal');
    if (!p) return null;
    return {
      exists: true,
      searchPlaceholder: (p.querySelector('.add-search') || {}).placeholder,
      cellCount: p.querySelectorAll('.add-cell').length,
      foot: (p.querySelector('.add-foot') || {}).textContent,
      title: (p.querySelector('.add-pal-title') || {}).textContent,
    };
  });
  // close
  await page.keyboard.press('Escape');
  await page.waitForTimeout(120);
  r.paletteClosedAfterEsc = await page.evaluate(() => !document.querySelector('.add-pal'));

  // 2) DOUBLE-CLICK empty canvas -> palette
  const box = await page.evaluate(() => {
    const a = document.getElementById('canvasArea').getBoundingClientRect();
    return { x: a.x, y: a.y, w: a.width, h: a.height };
  });
  // pick a spot in lower area (likely empty with default layout)
  const dx = box.x + Math.min(box.w - 40, 360);
  const dy = box.y + box.h - 80;
  await page.mouse.dblclick(dx, dy);
  await page.waitForTimeout(200);
  r.dblClickPalette = await page.evaluate(() => !!document.querySelector('.add-pal'));

  // 3) click a cell -> adds node at cursor, palette closes
  const before = await page.evaluate(() => document.querySelectorAll('.rf-node').length);
  await page.evaluate(() => { const c = document.querySelector('.add-pal .add-cell'); if (c) c.click(); });
  await page.waitForTimeout(200);
  r.addedNode = await page.evaluate(() => {
    return {
      after: document.querySelectorAll('.rf-node').length,
      paletteGone: !document.querySelector('.add-pal'),
    };
  });
  r.addedNode.delta = r.addedNode.after - before;

  // 4) EMPTY-canvas hint toggle (drive via state if accessible)
  r.hintTest = await page.evaluate(() => {
    try {
      if (typeof state === 'undefined') return 'state-not-accessible';
      state.nodes = [];
      renderNodes();
      const empty = getComputedStyle(document.getElementById('canvasHint')).display;
      // add one back
      addNode('text');
      const after = getComputedStyle(document.getElementById('canvasHint')).display;
      return { emptyDisplay: empty, afterAddDisplay: after };
    } catch (e) { return 'ERR:' + e.message; }
  });

  r.consoleErrors = errors;
  console.log(JSON.stringify(r, null, 2));
  await browser.close();
})();
