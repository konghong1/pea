const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const file = path.resolve(__dirname, 'pea-canvas-v9.html');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  await page.goto('file://' + file);
  await page.waitForTimeout(800);
  // go to canvas page
  await page.click('[data-page="canvas"]');
  await page.waitForTimeout(400);
  // open the bottom add bar
  await page.click('#addBtn');
  await page.waitForTimeout(400);
  // type something to show the textarea active state
  await page.fill('#addPopInput', 'a futuristic neon city at night');
  await page.waitForTimeout(300);
  // screenshot just the canvas area region (full viewport is fine)
  await page.screenshot({ path: 'v9_canvas_addbar.png' });
  console.log('screenshot saved: v9_canvas_addbar.png');
  await browser.close();
})();
