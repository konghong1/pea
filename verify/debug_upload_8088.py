import os, sys, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
EMAIL = f"dbg_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
HERE = os.path.dirname(os.path.abspath(__file__))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    ctx = browser.new_context(viewport={"width":1440,"height":900})
    page = ctx.new_page()
    # 8088 prod 需要 dev hooks 才暴露 window.__canvas
    page.add_init_script("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}")
    uploads = []
    page.on("response", lambda r: uploads.append((r.status, r.url[-40:])) if "/files/upload" in r.url else None)
    page.on("console", lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error","warning") else None)
    page.on("pageerror", lambda e: print("[pageerror]", e))

    page.goto(BASE, wait_until="networkidle"); page.wait_for_timeout(1000)
    page.get_by_role("button", name="没有账号？去注册").first.click(); page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "DbgBot")
    page.locator("form button[type=submit]").click(); page.wait_for_timeout(4000)
    cid = page.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'dbg',scope:'personal'})});
        return (await r.json()).id;
    }""")
    print("canvas id:", cid)
    page.evaluate(f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))")
    page.wait_for_selector(".react-flow__viewport", timeout=20000)
    page.wait_for_timeout(1500)
    page.evaluate("""() => {
        const store = window.__canvas.getState();
        const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
        const nImg = mk('nImg','image',150,200,{prompt:'',meta:{}});
        store.loadGraph([nImg],[], store.version);
        store.select('nImg');
        return true;
    }""")
    page.wait_for_timeout(2000)

    def st():
        return page.evaluate("""() => {
            const n = window.__canvas.getState().nodes.find(x=>x.id==='nImg');
            return { fileKey:n?.data?.fileKey||null, url:n?.data?.url||null };
        }""")
    inp = page.locator('.react-flow__node[data-id="nImg"] input[type=file]')
    print("8088 BEFORE:", st(), "uploads:", uploads)
    inp.set_input_files(os.path.join(HERE,"t1.png"), timeout=15000); page.wait_for_timeout(4000)
    print("8088 AFTER #1:", st(), "uploads:", uploads)
    inp.set_input_files(os.path.join(HERE,"t2.png"), timeout=15000); page.wait_for_timeout(4000)
    print("8088 AFTER #2:", st(), "uploads:", uploads)
    browser.close(); sys.exit(0)
