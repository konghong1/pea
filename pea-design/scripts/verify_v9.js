const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const file = path.resolve(__dirname, 'pea-canvas-v9.html');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  await page.goto('file://' + file);
  await page.waitForTimeout(800);

  // Switch to canvas page
  await page.click('[data-page="canvas"]');
  await page.waitForTimeout(400);

  // Click add button to open bottom bar
  await page.click('#addBtn');
  await page.waitForTimeout(300);

  const checks = await page.evaluate(() => {
    const bar = document.querySelector('#addPop');
    const inp = document.getElementById('addPopInput');
    const model = bar ? bar.querySelector('.add-pal-model') : null;
    const chips = bar ? [...bar.querySelectorAll('.add-pal-chip')] : [];
    const rightTools = bar ? [...bar.querySelectorAll('.add-pal-righttools .add-pal-act, .add-pal-righttools .add-pal-send')] : [];
    const send = bar ? bar.querySelector('.add-pal-send') : null;
    const badge = bar ? bar.querySelector('.add-pal-badge') : null;
    const style = bar ? window.getComputedStyle(bar) : {};
    return {
      barExists: !!bar,
      inputExists: !!inp,
      inputPlaceholder: inp ? inp.placeholder : '',
      modelText: model ? model.textContent : '',
      chips: chips.map(c => c.textContent.trim()),
      rightToolCount: rightTools.length,
      sendExists: !!send,
      badgeText: badge ? badge.textContent : '',
      position: style.position,
      bottom: style.bottom,
      left: style.left,
      transform: style.transform
    };
  });

  console.log('CHECKS:', JSON.stringify(checks, null, 2));

  const ok =
    checks.barExists &&
    checks.inputExists &&
    checks.inputPlaceholder === '描述任何你想要生成的内容' &&
    checks.modelText.includes('Seedream 5.0 Lite') &&
    checks.chips.includes('☐ 1:1') &&
    checks.chips.includes('2K') &&
    checks.rightToolCount >= 4 &&
    checks.sendExists &&
    checks.badgeText === '5' &&
    checks.position === 'fixed';

  if (!ok) {
    console.error('FAILED checks');
    await browser.close();
    process.exit(1);
  }

  // Test typing and sending adds a node
  await page.fill('#addPopInput', 'a futuristic city');
  await page.waitForTimeout(200);
  const before = await page.evaluate(() => state.nodes.length);
  await page.click('.add-pal-send');
  await page.waitForTimeout(300);
  const after = await page.evaluate(() => state.nodes.length);

  console.log('before:', before, 'after:', after, 'consoleErrors:', errors);

  if (after <= before) {
    console.error('Node not added');
    await browser.close();
    process.exit(1);
  }

  // Test double-click on empty canvas opens bar
  await page.dblclick('#canvasArea', { position: { x: 300, y: 250 } });
  await page.waitForTimeout(300);
  const bar2 = await page.evaluate(() => !!document.getElementById('addPop'));
  if (!bar2) {
    console.error('Double-click did not open bar');
    await browser.close();
    process.exit(1);
  }

  if (errors.length > 0) {
    console.error('Console errors:', errors);
    await browser.close();
    process.exit(1);
  }

  console.log('v9 bottom bar: ALL OK');
  await browser.close();
})();
