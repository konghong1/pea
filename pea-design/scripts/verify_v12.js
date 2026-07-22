const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const file = path.resolve('pea-canvas-v12.html');
  await page.goto('file://' + file);
  await page.waitForTimeout(1200);

  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  // Default state (agent node pre-selected -> image mode add bar)
  const defaultChecks = await page.evaluate(() => {
    const p = document.getElementById('addPop');
    const model = document.querySelector('.add-pal-model');
    const badge = document.querySelector('.add-pal-badge');
    const leftBtns = document.querySelectorAll('.add-pal-tools .add-pal-ibtn');
    return {
      paletteVisible: !!(p && p.isConnected && p.getBoundingClientRect().width > 0),
      modelText: model ? model.textContent.trim() : null,
      badgeText: badge ? badge.textContent.trim() : null,
      leftBtnCount: leftBtns.length,
      leftBtnIcons: [...leftBtns].map(b => b.textContent.trim()),
    };
  });

  // Select text node
  await page.click('#node1');
  await page.waitForTimeout(400);

  const textChecks = await page.evaluate(() => {
    const p = document.getElementById('addPop');
    const model = document.querySelector('.add-pal-model');
    const badge = document.querySelector('.add-pal-badge');
    const leftBtns = document.querySelectorAll('.add-pal-tools .add-pal-ibtn');
    const tb = document.getElementById('textNodeToolbar');
    const node = document.getElementById('node1');
    const nodeRect = node ? node.getBoundingClientRect() : null;
    const tbRect = tb ? tb.getBoundingClientRect() : null;
    return {
      paletteVisible: !!(p && p.isConnected && p.getBoundingClientRect().width > 0),
      modelText: model ? model.textContent.trim() : null,
      badgeText: badge ? badge.textContent.trim() : null,
      leftBtnCount: leftBtns.length,
      leftBtnIcons: [...leftBtns].map(b => b.textContent.trim()),
      toolbarVisible: !!(tb && tb.isConnected && tb.getBoundingClientRect().width > 0),
      toolbarAboveNode: !!(nodeRect && tbRect && tbRect.bottom <= nodeRect.top + 2),
      toolbarText: tb ? tb.innerText.replace(/\s+/g, ' ').slice(0, 80) : null,
    };
  });

  await page.screenshot({ path: 'v12_text_node_selected.png', fullPage: false });

  // Select image node
  await page.click('#node3');
  await page.waitForTimeout(400);

  const imageChecks = await page.evaluate(() => {
    const p = document.getElementById('addPop');
    const model = document.querySelector('.add-pal-model');
    const badge = document.querySelector('.add-pal-badge');
    const leftBtns = document.querySelectorAll('.add-pal-tools .add-pal-ibtn');
    const chips = document.querySelectorAll('.add-pal-chip');
    return {
      paletteVisible: !!(p && p.isConnected && p.getBoundingClientRect().width > 0),
      modelText: model ? model.textContent.trim() : null,
      badgeText: badge ? badge.textContent.trim() : null,
      leftBtnCount: leftBtns.length,
      leftBtnIcons: [...leftBtns].map(b => b.textContent.trim()),
      chipTexts: [...chips].map(c => c.textContent.trim()),
    };
  });

  await page.screenshot({ path: 'v12_image_node_selected.png', fullPage: false });

  await browser.close();
  console.log(JSON.stringify({ defaultChecks, textChecks, imageChecks, consoleErrors: errors }, null, 2));
})();
