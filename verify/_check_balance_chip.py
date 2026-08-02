"""Verify balance chip redesign - screenshot + DOM probe."""
import uuid, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
OUT_DEFAULT = "verify/shot_balance_chip.png"
OUT_HOVER = "verify/shot_balance_chip_hover.png"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    ctx = browser.new_context(viewport={"width":1440,"height":900}, device_scale_factor=2)
    page = ctx.new_page()
    page.on("console", lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error","warning") else None)
    page.add_init_script("localStorage.setItem('__peaDevHooks','1')")
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    # login / register
    try:
        page.locator("text=没有账号？去注册").first.click(timeout=4000)
        page.wait_for_timeout(400)
        email = f"bal_{uuid.uuid4().hex[:8]}@pea.ai"
        page.fill('input[placeholder="you@pea.ai"]', email)
        page.fill('input[placeholder="至少 8 位"]', "test1234")
        page.fill('input[placeholder="可选"]', "Bal")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(2000)
        page.wait_for_selector("text=新建项目", timeout=15000)
    except Exception as e:
        print(f"[register] skipped: {e}")

    # create canvas
    cid = page.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/api/canvases', {
            method:'POST',
            headers:{'Content-Type':'application/json', ...(token?{Authorization:`Bearer ${token}`}:{})},
            body:JSON.stringify({title:'bal-test',scope:'personal'})
        });
        return (await r.json()).id;
    }""")
    print(f"cid={cid}")

    # navigate to canvas editor (via workspace click)
    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    # click the project card to enter canvas editor
    try:
        card = page.locator(f'[data-canvas-id="{cid}"]')
        card.wait_for(state="visible", timeout=8000)
        card.click()
        page.wait_for_timeout(2500)
    except Exception as e:
        print(f"[card-click] failed: {e}")
        # fallback: direct navigation
        page.goto(f"{BASE}/canvas/{cid}", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

    # wait for balance chip
    chip = page.locator(".pea-canvas-tapies")
    chip.wait_for(state="visible", timeout=15000)
    box = chip.bounding_box()
    print(f"chip box: {box}")

    # DOM probe
    info = page.evaluate("""() => {
        const c = document.querySelector('.pea-canvas-tapies');
        if(!c) return {found:false};
        const cs = getComputedStyle(c);
        const gem = c.querySelector('.pea-balance-gem');
        const num = c.querySelector('.pea-balance-num');
        const oldWallet = c.querySelector('.anticon-wallet');  // antd WalletOutlined class
        return {
            found:true,
            w:cs.width, h:cs.height,
            bg:cs.backgroundImage.slice(0,60),
            border:cs.border,
            boxShadow:cs.boxShadow.slice(0,80),
            backdrop:cs.backdropFilter,
            hasGem: !!gem,
            hasBalanceNum: !!num,
            hasOldWallet: !!oldWallet,
            numText: num ? num.textContent : null,
            gemW: gem ? getComputedStyle(gem).width : null,
            gemH: gem ? getComputedStyle(gem).height : null,
        };
    }""")
    for k,v in info.items():
        print(f"  {k}: {v}")

    # screenshot default state
    if box:
        pad = 16
        page.screenshot(path=OUT_DEFAULT, clip={
            "x": max(0, box["x"]-pad),
            "y": max(0, box["y"]-pad),
            "width": box["width"]+pad*2,
            "height": box["height"]+pad*2,
        })
        print(f"screenshot -> {OUT_DEFAULT}")

    # hover screenshot
    chip.hover()
    page.wait_for_timeout(700)
    if box:
        page.screenshot(path=OUT_HOVER, clip={
            "x": max(0, box["x"]-pad),
            "y": max(0, box["y"]-pad),
            "width": box["width"]+pad*2,
            "height": box["height"]+pad*2,
        })
        print(f"hover screenshot -> {OUT_HOVER}")

    browser.close()
    print("\nDone.")
