import os, sys, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5174"
EMAIL = f"dbg_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
HERE = os.path.dirname(os.path.abspath(__file__))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    ctx = browser.new_context(viewport={"width":1440,"height":900})
    page = ctx.new_page()

    uploads = []
    page.on("response", lambda r: uploads.append((r.status, r.url)) if "/files/upload" in r.url else None)
    page.on("console", lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error","warning") else None)
    page.on("pageerror", lambda e: print("[pageerror]", e))

    page.goto(BASE, wait_until="networkidle"); page.wait_for_timeout(800)
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
    page.evaluate(f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))")
    page.wait_for_selector(".react-flow__viewport", timeout=20000)
    page.wait_for_timeout(1000)

    # 注入一个「AI 生成」image 节点（有 resultUrl，模拟用户真实场景）
    page.evaluate("""() => {
        const store = window.__canvas.getState();
        const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
        const nImg = mk('nImg','image',150,200,{resultUrl:'https://placehold.co/120x120/1fa2dc/ffffff?text=AI',resultUrls:['https://placehold.co/120x120/1fa2dc/ffffff?text=AI'],prompt:'一只猫',meta:{}});
        store.loadGraph([nImg],[], store.version);
        store.select('nImg');
        return true;
    }""")
    page.wait_for_timeout(2000)

    def node_state():
        return page.evaluate("""() => {
            const s = window.__canvas.getState();
            const n = s.nodes.find(x=>x.id==='nImg');
            return { fileKey: n?.data?.fileKey||null, url: n?.data?.url||null, resultUrl: n?.data?.resultUrl||null, resultUrls:(n?.data?.resultUrls||[]).length };
        }""")

    inp = page.locator('.react-flow__node[data-id="nImg"] input[type=file]')
    print("BEFORE:", node_state())

    print(">>> upload #1")
    inp.set_input_files(os.path.join(HERE, "t1.png"), timeout=15000)
    page.wait_for_timeout(4000)
    print("AFTER #1:", node_state())
    print("upload responses so far:", uploads)

    print(">>> upload #2 (second image)")
    inp.set_input_files(os.path.join(HERE, "t2.png"), timeout=15000)
    page.wait_for_timeout(4000)
    print("AFTER #2:", node_state())
    print("upload responses total:", uploads)

    browser.close()
    sys.exit(0)
