import os, sys, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5174"
EMAIL = f"dbg_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    ctx = browser.new_context(viewport={"width":1440,"height":900})
    page = ctx.new_page()
    page.on("console", lambda m: print(f"[console:{m.type}] {m.text}"))
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
    print("canvas id:", cid)
    page.evaluate(f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))")
    page.wait_for_selector(".react-flow__viewport", timeout=20000)
    page.wait_for_timeout(1000)

    # 注入：nGen = 规范的 AI 生成图节点（resultUrls，无 fileKey）；nUp = 上传图节点（fileKey，无 resultUrl）
    page.evaluate("""() => {
        const store = window.__canvas.getState();
        const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
        const nGen = mk('nGen','image',150,200,{resultUrl:'https://placehold.co/120x120/1fa2dc/ffffff?text=AI',resultUrls:['https://placehold.co/120x120/1fa2dc/ffffff?text=AI'],prompt:'一只猫',meta:{}});
        const nUp  = mk('nUp','image',150,450,{fileKey:'u/test/up.png', url:'https://placehold.co/120x120/888/fff?text=UP', prompt:'', meta:{}});
        store.loadGraph([nGen,nUp],[], store.version);
        return true;
    }""")
    page.wait_for_timeout(1500)

    def inspect(sel_id, label):
        page.evaluate(f"window.__canvas.getState().select('{sel_id}')")
        page.wait_for_timeout(2000)
        st = page.evaluate("""() => {
            const s = window.__canvas.getState();
            const sel = s.nodes.find(n=>n.id===s.selectedId);
            const hasEditor = !!document.querySelector('.node-prompt-editor');
            const hasInputBar = !!document.querySelector('.node-input-bar');
            const hasRefBar = !!document.querySelector('.node-ref-bar');
            return {
                selectedId: s.selectedId,
                selData: sel ? {kind:sel.data.kind, fileKey:sel.data.fileKey||null, url:sel.data.url||null, resultUrl:sel.data.resultUrl||null, resultUrls:(sel.data.resultUrls||[]).length} : null,
                hasEditor, hasInputBar, hasRefBar,
                isUploadedMedia_approx: !!(sel && (sel.data.kind==='image'||sel.data.kind==='video') && !!(sel.data.fileKey||sel.data.url) && !(sel.data.resultUrl||(sel.data.resultUrls&&sel.data.resultUrls.length)))
            };
        }""")
        print(f"--- {label} ({sel_id}) ---")
        print("   ", st)
        return st

    inspect('nGen', 'AI生成图节点')
    inspect('nUp', '用户上传图节点')

    browser.close()
    sys.exit(0)
