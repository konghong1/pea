import uuid, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
OUT = "verify/shot_launcher_v3.png"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    page.on("console", lambda m: print(f"[c:{m.type}] {m.text}") if m.type in ("error","warning") else None)
    page.add_init_script("localStorage.setItem('__peaDevHooks','1')")
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    try:
        page.locator("text=没有账号？去注册").first.click(timeout=4000)
        page.wait_for_timeout(400)
        email = f"dbg_{uuid.uuid4().hex[:8]}@pea.ai"
        page.fill('input[placeholder="you@pea.ai"]', email)
        page.fill('input[placeholder="至少 8 位"]', "test1234")
        page.fill('input[placeholder="可选"]', "Dbg")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(2000)
        page.wait_for_selector("text=新建项目", timeout=15000)
    except Exception as e:
        print("register skipped:", repr(e))

    cid = page.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/api/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'dbg',scope:'personal'})});
        const t = await r.text();
        try { return JSON.parse(t).id; } catch(e){ return 'ERR:'+t.slice(0,200);}
    }""")
    print("cid:", cid)
    page.goto(f"{BASE}/workspace", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.locator(f'[data-canvas-id="{cid}"]').first.click(timeout=8000)
    page.wait_for_timeout(3000)

    rep1 = page.evaluate("""() => ({
        url: location.href, rf: !!document.querySelector('.react-flow'),
        nodes: document.querySelectorAll('.react-flow__node').length,
        launcher: !!document.querySelector('.pe-launcher')
    })""")
    print("after open:", json.dumps(rep1, ensure_ascii=False))

    if not rep1.get("rf"):
        print("editor not opened, abort")
        page.screenshot(path="verify/_diag_no_editor.png")
        browser.close(); raise SystemExit(1)

    # add a node: double-click pane center to open library, pick 图片
    if not rep1.get("nodes"):
        pane = page.locator(".react-flow__pane").first
        b = pane.bounding_box()
        page.mouse.dblclick(b["x"]+b["width"]/2, b["y"]+b["height"]/2)
        page.wait_for_timeout(800)
        page.locator(".pea-add-menu-item", has_text="图片").first.click(timeout=6000)
        page.wait_for_timeout(1500)
        print("added image node")

    try:
        page.locator(".pe-launcher").first.wait_for(state="visible", timeout=12000)
    except Exception as e:
        print("launcher not visible:", repr(e))
        page.screenshot(path="verify/_diag_no_launcher.png")
        browser.close(); raise SystemExit(1)

    box = page.locator(".pe-launcher").first.bounding_box()
    print("launcher box:", box)
    info = page.evaluate("""() => {
        const l = document.querySelector('.pe-launcher');
        const cs = getComputedStyle(l);
        const num = l.querySelector('.pe-cost-num');
        const trig = l.querySelector('.pe-trigger');
        return {
            launcherW: cs.width, launcherH: cs.height,
            hasT: !!l.querySelector('.pe-cost-lbl'),
            hasOldRocket: !!l.querySelector('.pe-rocket'),
            numText: num? num.textContent : null,
            hasGenIcon: !!l.querySelector('.pe-gen-icon'),
            hasSpark: !!l.querySelector('.pe-gen-spark'),
            particleCount: l.querySelectorAll('.pe-particle').length,
            triggerBg: trig? getComputedStyle(trig).backgroundImage.slice(0,40): null
        };
    }""")
    print("DOM:", json.dumps(info, ensure_ascii=False))
    if box:
        page.screenshot(path=OUT, clip={"x": max(0, box['x']-24), "y": max(0, box['y']-24), "width": box['width']+48, "height": box['height']+48})
        print("screenshot ->", OUT)
        page.locator(".pe-launcher").first.hover()
        page.wait_for_timeout(700)
        page.screenshot(path="verify/shot_launcher_v3_hover.png", clip={"x": max(0, box['x']-24), "y": max(0, box['y']-24), "width": box['width']+48, "height": box['height']+48})
        print("hover screenshot -> verify/shot_launcher_v3_hover.png")
    browser.close()
