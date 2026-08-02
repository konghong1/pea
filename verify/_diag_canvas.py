import uuid, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
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
    page.goto(f"{BASE}/canvas/{cid}", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    # report structure
    rep = page.evaluate("""() => {
        const out = {};
        out.url = location.href;
        out.buttons = Array.from(document.querySelectorAll('button')).slice(0,30).map(b=>b.textContent.trim().slice(0,20));
        out.hasReactFlow = !!document.querySelector('.react-flow');
        out.nodes = document.querySelectorAll('.react-flow__node').length;
        out.launcher = !!document.querySelector('.pe-launcher');
        out.bodyText = document.body.innerText.slice(0,300);
        return out;
    }""")
    print("REPORT:", json.dumps(rep, ensure_ascii=False)[:1500])
    page.screenshot(path="verify/_diag_canvas.png", full_page=False)
    print("shot -> verify/_diag_canvas.png")
    browser.close()
