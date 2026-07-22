const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));

  const file = 'file://' + path.resolve('pea-canvas-v6.html');
  await page.goto(file, { waitUntil: 'load' });
  await page.waitForTimeout(400);

  const report = await page.evaluate(() => {
    const out = {};
    function clickBtn(sel){ const b=document.querySelector(sel); if(b) b.click(); }
    // open popup
    clickBtn('button[onclick="openUserMenu(event)"]');
    const menu = document.getElementById('userMenu');
    out.popupOpen = !!menu;
    if (menu) {
      out.popupName = (document.getElementById('umName')||{}).textContent;
      out.popupMail = (document.getElementById('umMail')||{}).textContent;
      out.popupStats = [...document.querySelectorAll('#userMenu .us-num')].map(n=>n.textContent);
      out.menuItems = [...document.querySelectorAll('#userMenu .ctx-item')].map(i=>i.textContent.replace(/\s+/g,''));
      out.hasViewHome = !!document.querySelector('#userMenu .um-btn.primary');
    }
    // 我的作品
    const worksItem = [...document.querySelectorAll('#userMenu .ctx-item')].find(i=>i.textContent.includes('我的作品'));
    if (worksItem) worksItem.click();
    out.drawerOpen = document.getElementById('acctDrawer').classList.contains('open');
    out.worksTabVisible = getComputedStyle(document.getElementById('acctTab-works')).display !== 'none';
    out.worksStats = ['wTotal','wApproved','wPrime','wStars','wFollow','wFollowing'].map(id=>(document.getElementById(id)||{}).textContent);

    // 通知偏好
    openAccountSettings('notif');
    const nl = document.getElementById('notifList');
    out.notifRows = nl ? nl.children.length : 0;
    // toggle first + save
    const firstToggle = nl && nl.querySelector('.ai-toggle');
    if (firstToggle) firstToggle.click();
    saveNotif();
    out.notifSaved = !!localStorage.getItem('tn_notif');

    // AI 提供商 (账户设置)
    openAccountSettings('settings');
    out.aiRows = document.getElementById('aiProviderList').children.length;
    out.aiDefOptions = document.getElementById('fDefProvider').options.length;

    // 个人资料 prefilled from live data
    openAccountSettings('profile');
    out.fNick = document.getElementById('fNick').value;
    out.fEmail = document.getElementById('fEmail').value;
    out.fBio = document.getElementById('fBio').value;

    // 保存个人资料持久化
    document.getElementById('fNick').value = '设计喵';
    saveAccount('profile');
    out.profilePersisted = (localStorage.getItem('tn_account')||'').includes('设计喵');
    closeAccountSettings();
    return out;
  });

  report.consoleErrors = errors;
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
})();
