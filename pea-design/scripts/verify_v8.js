const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = [];
  page.on('console', msg => { if (msg.type() === 'error') errs.push(msg.text()); });
  
  await page.goto('file:///D:/workspace/ai-agent/pea-canvas-v8.html', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);

  // ── Test 1: Workspace chat UI (Screenshot 2) ──
  const wsGreeting = await page.textContent('.ws-greeting');
  const wsPrompt = await page.textContent('.wsa-prompt');
  const cards = await page.$$eval('.wsa-card', els => els.length);
  const cardTitles = await page.$$eval('.wsa-card-title', els => els.map(e => e.textContent.trim()));
  const pluginTag = await page.$('.wsa-plugin-tag');
  const chatBox = await page.$('.wsa-chat-box');
  const textarea = await page.$('.wsa-textarea');
  const confirmBtn = await page.$('.wsa-confirm');
  const modelBtn = await page.$('.wsa-chat-model');
  const sendBtn = await page.$('.wsa-send-lg');

  console.log('── Workspace Chat (Screenshot 2) ──');
  console.log(`greeting: "${wsGreeting}" | ${wsGreeting.includes('wah1763751448') ? 'OK' : 'MISSING USER'}`);
  console.log(`prompt: "${wsPrompt}" | ${wsPrompt.includes('创作') ? 'OK' : 'WRONG'}`);
  console.log(`cards: ${cards} (expect 2) | titles: ${JSON.stringify(cardTitles)}`);
  console.log(`pluginTag: ${pluginTag ? 'OK' : 'MISSING'} | chatBox: ${chatBox ? 'OK' : 'MISSING'}`);
  console.log(`textarea: ${textarea ? 'OK' : 'MISSING'} | placeholder: "${await textarea.evaluate(el => el.placeholder)}"`);
  console.log(`confirmBtn: ${confirmBtn ? 'OK' : 'MISSING'} | text: "${await confirmBtn.evaluate(el => el.textContent.trim())}"`);
  console.log(`modelBtn: ${modelBtn ? 'OK' : 'MISSING'} | text: "${await modelBtn.evaluate(el => el.textContent.trim())}"`);
  console.log(`sendBtn: ${sendBtn ? 'OK' : 'MISSING'}`);

  // ── Test 2: Canvas Add Palette (Screenshot 1) ──
  // Switch to canvas and click the + button
  await page.click('[data-page="canvas"]');
  await page.waitForTimeout(300);
  await page.click('#addBtn');
  await page.waitForTimeout(300);

  const pal = await page.$('.add-pal');
  const palTop = await page.$('.add-pal-top');
  const palInput = await page.$('.add-pal-input');
  const palBar = await page.$('.add-pal-bar');
  const palModel = await page.$('.add-pal-model');
  const palSend = await page.$('.add-pal-send');
  const palIbtns = await page.$$eval('.add-pal-ibtn', els => els.length);

  console.log('\n── Canvas Add Palette (Screenshot 1) ──');
  console.log(`palette: ${pal ? 'OK' : 'MISSING'}`);
  console.log(`topRow: ${palTop ? 'OK' : 'MISSING'} | iconBtns: ${palIbtns} (expect 2)`);
  console.log(`input: ${palInput ? 'OK' : 'MISSING'} | placeholder: "${await palInput.evaluate(el => el.placeholder)}"`);
  console.log(`bar: ${palBar ? 'OK' : 'MISSING'}`);
  console.log(`model: ${palModel ? 'OK' : 'MISSING'} | text: "${await palModel.evaluate(el => el.textContent.trim())}"`);
  console.log(`send: ${palSend ? 'OK' : 'MISSING'}`);

  // Check palette visual style
  const palStyle = await pal.evaluate(el => {
    const cs = getComputedStyle(el);
    return { w: cs.width, radius: cs.borderRadius, bg: cs.backgroundColor.substring(0,18) };
  });
  console.log(`style: width=${palStyle.w} radius=${palStyle.radius} bg≈${palStyle.bg}`);

  // ── Test 3: Send from workspace ──
  await page.click('[data-page="workspace"]');
  await page.waitForTimeout(200);
  await page.fill('#wsInput', 'test workspace send');
  await page.click('#wsSendBtn');
  await page.waitForTimeout(200);
  const toastVisible = await page.$('.toast');
  console.log(`\n── Workspace Send ──`);
  console.log(`toast after send: ${toastVisible ? 'OK' : 'MISSING'}`);

  // ── Summary ──
  console.log('\n═══ SUMMARY ═══');
  const checks = [
    ['workspace greeting has username', wsGreeting.includes('wah1763751448')],
    ['workspace prompt correct', wsPrompt.includes('创作')],
    ['suggestion cards = 2', cards === 2],
    ['card1 = Seedance', cardTitles[0].includes('Seedance')],
    ['card2 = 创作记忆', cardTitles[1].includes('创作记忆')],
    ['plugin tag exists', !!pluginTag],
    ['chat box exists', !!chatBox],
    ['textarea exists', !!textarea],
    ['confirm btn exists', !!confirmBtn],
    ['model btn exists', !!modelBtn],
    ['send btn exists', !!sendBtn],
    ['canvas palette exists', !!pal],
    ['palette icon buttons = 2', palIbtns === 2],
    ['palette input exists', !!palInput],
    ['palette model = Gemini', (await palModel?.evaluate(el => el.textContent)).includes('Gemini')],
    ['palette send button', !!palSend],
    ['console errors = 0', errs.length === 0],
  ];
  let pass = 0;
  checks.forEach(([n, ok]) => { console.log(`${ok ? '✅' : '❌'} ${n}`); if(ok) pass++; });
  console.log(`\n${pass}/${checks.length} passed`);
  if (errs.length) console.log('Errors:', errs);

  await browser.close();
  process.exit(pass === checks.length ? 0 : 1);
})();
