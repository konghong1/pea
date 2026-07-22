const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const errors = [];
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('PAGEERR: ' + e.message));

  const fileUrl = 'file://' + path.resolve('D:/workspace/ai-agent/pea-canvas-v10.html');
  await page.goto(fileUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);

  const res = {};

  // ---- CANVAS PAGE ----
  // switch to canvas
  await page.evaluate(() => { const b = [...document.querySelectorAll('[onclick]')].find(e => /switchPage\(['"]canvas/.test(e.getAttribute('onclick')||'')); if (b) b.click(); });
  await page.waitForTimeout(300);

  res.nodeCount = await page.$$eval('.rf-node', els => els.length);
  // open add-pal (click + button)
  res.addBtnExists = await page.$('#addBtn') ? true : false;
  await page.evaluate(() => { const b = document.querySelector('#addBtn'); if (b) b.click(); });
  await page.waitForTimeout(250);
  res.addPalVisible = await page.$eval('.add-pal', el => { const r = el.getBoundingClientRect(); return r.width>0 && getComputedStyle(el).backgroundColor; }).catch(()=>false);
  res.addPalSendColor = await page.$eval('.add-pal-send', el => getComputedStyle(el).backgroundColor).catch(()=>null);
  res.addPalModelTxt = await page.$eval('.add-pal-model', el => el.textContent.trim()).catch(()=>null);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(150);

  // click a node -> inspector popup
  await page.evaluate(() => { const n = document.querySelector('.rf-node'); if (n) n.click(); });
  await page.waitForTimeout(250);
  res.inspectorVisible = await page.$eval('#inspector', el => el.classList.contains('open') || getComputedStyle(el).display !== 'none').catch(()=>false);
  res.inspectorBg = await page.$eval('#inspector', el => getComputedStyle(el).backgroundColor).catch(()=>null);

  // ---- WORKSPACE CHAT PAGE ----
  await page.evaluate(() => { const b = [...document.querySelectorAll('[onclick]')].find(e => /switchPage\(['"]workspace/.test(e.getAttribute('onclick')||'')); if (b) b.click(); });
  await page.waitForTimeout(300);
  res.chatInputVisible = await page.$('.wsa-textarea') ? true : false;
  res.chatSendColor = await page.$eval('.wsa-send-lg', el => getComputedStyle(el).backgroundColor).catch(()=>null);

  // ---- SCREENSHOTS for human comparison ----
  await page.evaluate(() => { const b = [...document.querySelectorAll('[onclick]')].find(e => /switchPage\(['"]canvas/.test(e.getAttribute('onclick')||'')); if (b) b.click(); });
  await page.waitForTimeout(300);
  await page.evaluate(() => { const b = document.querySelector('#addBtn'); if (b) b.click(); });
  await page.waitForTimeout(250);
  await page.screenshot({ path: 'v10_canvas_addbar.png' });
  await page.keyboard.press('Escape');
  // node selected screenshot
  await page.evaluate(() => { const n = document.querySelector('.rf-node'); if (n) n.click(); });
  await page.waitForTimeout(250);
  await page.screenshot({ path: 'v10_canvas_node_popup.png' });

  res.consoleErrors = errors;
  console.log(JSON.stringify(res, null, 2));
  await browser.close();
})();
