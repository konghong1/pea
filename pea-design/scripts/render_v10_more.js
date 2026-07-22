const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  const url = 'file://' + path.resolve('D:/workspace/ai-agent/pea-canvas-v10.html');
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);

  // workspace chat page
  await page.evaluate(() => { const b=[...document.querySelectorAll('[onclick]')].find(e=>/switchPage\(['"]workspace/.test(e.getAttribute('onclick')||'')); b&&b.click(); });
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'v10_workspace_chat.png' });

  // account center drawer
  await page.evaluate(() => { const b=document.querySelector('[onclick*="openAccountSettings"]'); b&&b.click(); });
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'v10_account_center.png' });

  console.log('errs:', JSON.stringify(errs));
  await browser.close();
})();
