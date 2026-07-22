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

  const r = {};

  // 1) Popup menu = real pea menu
  await page.evaluate(() => { switchPage('workspace'); });
  await page.click('#userAvatar').catch(() => {});
  // The avatar button triggers openUserMenu via onclick in v3 markup; click the avatar wrapper
  await page.evaluate(() => {
    const b = document.querySelector('[onclick^="openUserMenu"]');
    if (b) b.click();
  });
  await page.waitForTimeout(250);
  r.popupItems = await page.evaluate(() =>
    [...document.querySelectorAll('#userMenu .ctx-item')].map(i => i.textContent.replace(/\s+/g,''))
  );
  // expected real labels
  r.hasRealMenu = ['个人主页','我的通知','礼包超市','订阅套餐','使用教程','帮助中心','快捷键','反馈问题','加入Discord社群','联系我们','退出登录']
    .every(l => r.popupItems.join('').includes(l.replace(/[\s·]/g,'')));

  // 2) Open 账户管理 (drawer) via popup 账户管理 button
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('#userMenu .um-btn')].find(x => x.textContent.includes('账户管理'));
    if (b) b.click();
  });
  await page.waitForTimeout(350);
  r.drawerOpen = await page.evaluate(() => document.getElementById('acctDrawer').classList.contains('open'));
  r.drawerTitle = await page.evaluate(() => { const t=document.querySelector('#acctDrawer .acct-title'); return t?t.textContent:null; });
  r.sidebarNavs = await page.evaluate(() =>
    [...document.querySelectorAll('#acctDrawer .acct-nav')].map(n => n.textContent.trim())
  );

  // 3) profile pane default visible + fields
  r.profileVisible = await page.evaluate(() => document.getElementById('pane-profile').classList.contains('active'));
  r.fNick = await page.evaluate(() => document.getElementById('fNick').value);
  r.fBio = await page.evaluate(() => document.getElementById('fBio').value);

  // 4) switch to 通用设置 pane
  await page.evaluate(() => switchAcctPane('general', null));
  await page.waitForTimeout(120);
  r.generalVisible = await page.evaluate(() => document.getElementById('pane-general').classList.contains('active'));
  r.langOptions = await page.evaluate(() => [...document.getElementById('fLang').options].map(o=>o.textContent));

  // 5) AI provider pane renders rows
  await page.evaluate(() => switchAcctPane('aiprov', null));
  await page.waitForTimeout(150);
  r.aiRows = await page.evaluate(() => document.querySelectorAll('#aiProviderList .ai-prov-row').length);
  r.aiDefOptions = await page.evaluate(() => document.getElementById('fDefProvider').options.length);

  // 6) billing pane labels
  await page.evaluate(() => switchAcctPane('billing', null));
  await page.waitForTimeout(120);
  r.billingLabels = await page.evaluate(() =>
    [...document.querySelectorAll('#pane-billing .abt')].map(b=>b.textContent)
  );

  // 7) invite pane + copyInvite exists
  await page.evaluate(() => switchAcctPane('invite', null));
  await page.waitForTimeout(120);
  r.inviteVisible = await page.evaluate(() => document.getElementById('pane-invite').classList.contains('active'));

  // 8) notif pane renders
  await page.evaluate(() => switchAcctPane('notif', null));
  await page.waitForTimeout(150);
  r.notifRows = await page.evaluate(() => document.querySelectorAll('#notifList .notif-row').length);

  // 9) save profile persists + toast
  await page.evaluate(() => { switchAcctPane('profile', null); document.getElementById('fNick').value='wah_new'; saveAccount('profile'); });
  await page.waitForTimeout(150);
  r.savedToast = await page.evaluate(() => (window.__lastToast||'') );
  r.persisted = await page.evaluate(() => { try { return JSON.parse(localStorage.getItem('tn_account')||'{}').nick; } catch(e){ return null; } });
  // restore for cleanliness
  await page.evaluate(() => { localStorage.removeItem('tn_account'); });

  r.consoleErrors = errors;
  console.log(JSON.stringify(r, null, 2));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
