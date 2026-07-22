const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const file = path.resolve('pea-canvas-v11.html');
  await page.goto('file://' + file);
  await page.waitForTimeout(1200);

  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  // Open add palette and verify content before screenshot
  await page.evaluate(() => openAddPopover({ stopPropagation: () => {} }));
  await page.waitForTimeout(400);

  const paletteChecks = await page.evaluate(() => {
    const p = document.getElementById('addPop');
    const inp = document.getElementById('addPopInput');
    const model = document.querySelector('.add-pal-model');
    const badge = document.querySelector('.add-pal-badge');
    const leftBtns = document.querySelectorAll('.add-pal-tools .add-pal-ibtn');
    const rightBtns = document.querySelectorAll('.add-pal-righttools .add-pal-act');
    return {
      paletteVisible: !!(p && p.isConnected && p.getBoundingClientRect().width > 0),
      paletteRect: p ? p.getBoundingClientRect() : null,
      placeholder: inp ? inp.placeholder : null,
      modelText: model ? model.textContent.trim() : null,
      badgeText: badge ? badge.textContent.trim() : null,
      leftBtnCount: leftBtns.length,
      leftBtnIcons: [...leftBtns].map(b => b.textContent.trim()),
      rightBtnCount: rightBtns.length,
      rightBtnIcons: [...rightBtns].map(b => b.textContent.trim().slice(0, 4)),
    };
  });

  await page.screenshot({ path: 'v11_canvas_addbar.png', fullPage: false });

  // Close palette and select text node
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  await page.click('#node1');
  await page.waitForTimeout(400);

  const toolbarChecks = await page.evaluate(() => {
    const tb = document.getElementById('textNodeToolbar');
    return {
      toolbarVisible: !!(tb && tb.isConnected && tb.getBoundingClientRect().width > 0),
      toolbarRect: tb ? tb.getBoundingClientRect() : null,
      toolbarText: tb ? tb.innerText.replace(/\s+/g, ' ').slice(0, 80) : null,
    };
  });

  await page.screenshot({ path: 'v11_text_node_selected.png', fullPage: false });

  await browser.close();
  console.log(JSON.stringify({ paletteChecks, toolbarChecks, consoleErrors: errors }, null, 2));
})();
