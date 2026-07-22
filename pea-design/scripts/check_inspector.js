const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto('file://' + path.resolve('D:/workspace/ai-agent/pea-canvas-v10.html'), { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  await page.evaluate(() => { const b=[...document.querySelectorAll('[onclick]')].find(e=>/switchPage\(['"]canvas/.test(e.getAttribute('onclick')||'')); b&&b.click(); });
  await page.waitForTimeout(300);
  // click first node
  await page.evaluate(() => { const n=document.querySelector('.rf-node'); n&&n.dispatchEvent(new MouseEvent('mousedown',{bubbles:true})); });
  await page.waitForTimeout(300);
  const rp = await page.$eval('#rpBody', el => el.innerText.slice(0,120)).catch(()=>'(no rpBody)');
  const rpBg = await page.$eval('.right-panel', el => getComputedStyle(el).backgroundColor).catch(()=>null);
  const nodeSel = await page.$eval('.rf-node', el => el.classList.contains('selected')).catch(()=>false);
  console.log(JSON.stringify({ rpSnippet: rp, rpBg, nodeSelected: nodeSel, errs }, null, 2));
  await page.screenshot({ path: 'v10_node_selected.png' });
  await browser.close();
})();
