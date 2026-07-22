const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true, args: ['--no-sandbox', '--disable-gpu']
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('PAGEERR: ' + e.message));

  await page.goto('file:///D:/workspace/ai-agent/pea-canvas-v5.html');
  await page.waitForTimeout(1000);
  const R = {};

  // A. ecom dark theme: container background should be near-black, not white
  R.ecomTheme = await page.evaluate(() => {
    const pg = document.getElementById('page-ecom');
    const cs = getComputedStyle(pg);
    return { bg: cs.backgroundColor, color: cs.color };
  });

  // B. overflow check: #page-ecom must fit viewport, content scrolls internally
  R.overflow = await page.evaluate(() => {
    const pg = document.getElementById('page-ecom');
    const ca = document.querySelector('#page-ecom .content-area');
    const cfg = document.querySelector('#page-ecom .config-panel');
    return {
      pageFitsViewport: pg.getBoundingClientRect().bottom <= window.innerHeight + 1,
      contentScrolls: ca ? ca.scrollHeight > ca.clientHeight + 2 : false,
      configScrolls: cfg ? cfg.scrollHeight > cfg.clientHeight + 2 : false,
      contentClipped: ca ? (ca.getBoundingClientRect().bottom > window.innerHeight + 1) : false
    };
  });

  // C. switch to ecom + gallery still renders
  await page.evaluate(() => switchPage('ecom'));
  await page.waitForTimeout(300);
  R.gallery = await page.evaluate(() => {
    const g = document.getElementById('galleryGrid');
    return { cards: g ? g.querySelectorAll('.case-card').length : 0 };
  });

  // D. account popup enrichment
  await page.evaluate(() => switchPage('workspace'));
  await page.evaluate(() => openUserMenu({ stopPropagation(){} }));
  await page.waitForTimeout(200);
  R.popup = await page.evaluate(() => {
    const m = document.getElementById('userMenu');
    if (!m) return { exists: false };
    return {
      exists: true,
      hasName: !!m.querySelector('#umName'),
      hasPlan: !!m.querySelector('.um-plan'),
      hasPoints: !!m.querySelector('.um-points'),
      hasAiItem: !![...m.querySelectorAll('.ctx-item')].find(i => i.textContent.includes('AI 提供商')),
      itemCount: m.querySelectorAll('.ctx-item').length
    };
  });
  await page.evaluate(() => { const p = document.getElementById('userMenu'); if (p) p.remove(); });

  // E. AI provider config: open via menu entry, render list, toggle + persist
  await page.evaluate(() => openAiProviderConfig());
  await page.waitForTimeout(400);
  R.aiConfig = await page.evaluate(() => {
    const list = document.getElementById('aiProviderList');
    const rows = list ? list.querySelectorAll('.ai-prov-row').length : 0;
    const drawerOpen = document.getElementById('acctDrawer').classList.contains('open');
    // toggle the first provider off
    const toggles = list ? list.querySelectorAll('.ai-toggle') : [];
    let before = null, after = null;
    if (toggles[0]) {
      before = toggles[0].classList.contains('on');
      toggles[0].click();
      after = toggles[0].classList.contains('on');
    }
    let stored = null;
    try { stored = localStorage.getItem('tn_ai_providers'); } catch(e){}
    return { rows, drawerOpen, toggled: (before !== null && before !== after), stored: !!stored };
  });

  // F. settings save persists to localStorage
  R.settingsSave = await page.evaluate(() => {
    document.getElementById('fOcc').value = '电商设计师';
    saveAccount('settings');
    let stored = null;
    try { stored = localStorage.getItem('tn_account'); } catch(e){}
    let occ = null;
    if (stored) { try { occ = JSON.parse(stored).occ; } catch(e){} }
    return { saved: occ === '电商设计师' };
  });

  R.consoleErrors = errors;
  console.log(JSON.stringify(R, null, 2));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
