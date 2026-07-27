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
    # create canvas via API
    cid = page.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'dbg',scope:'personal'})});
        return (await r.json()).id;
    }""")
    print("canvas id:", cid)
    page.evaluate(f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))")
    page.wait_for_selector(".react-flow__viewport", timeout=20000)
    page.wait_for_timeout(1000)
    # inject
    page.evaluate("""() => {
        const store = window.__canvas.getState();
        store.loadGraph([], [], store.version);
        const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
        const imgNode = mk('nImg1','image',100,200,{resultUrl:'https://placehold.co/120x120/1fa2dc/ffffff?text=Ref+Img',meta:{fileName:'a.png'}});
        const textNode = mk('nText1','text',100,400,{html:'高端女装模特'});
        const target = mk('nTarget1','image',500,300,{prompt:'',meta:{}});
        store.loadGraph([imgNode,textNode,target],[{id:'e1',source:'nImg1',target:'nTarget1',type:'pea'},{id:'e2',source:'nText1',target:'nTarget1',type:'pea'}], store.version);
        store.select('nTarget1');
        return true;
    }""")
    page.wait_for_timeout(2500)
    state = page.evaluate("""() => {
        const s = window.__canvas.getState();
        const domNodes = Array.from(document.querySelectorAll('.react-flow__node')).map(el => el.getAttribute('data-id'));
        const tEl = document.querySelector('.react-flow__node[data-id=\"nTarget1\"]');
        let rect=null; if (tEl) { const r=tEl.getBoundingClientRect(); rect={x:r.x,y:r.y,w:r.width,h:r.height}; }
        return {
            selectedIds: s.selectedIds, selectedId: s.selectedId,
            nodeCount: s.nodes.length, nodeIds: s.nodes.map(n=>n.id),
            domNodes, targetDomRect: rect,
            hasInputBar: !!document.querySelector('.node-input-bar'),
            hasRefThumb: !!document.querySelector('.node-ref-thumb'),
            inputBarCount: document.querySelectorAll('.node-input-bar').length
        };
    }""")
    print("STATE:", state)

    # ── 模拟「点击上传」：给已选中的图片节点写入 fileKey，isUploadedMedia 翻转为 true ──
    page.evaluate("""() => {
        const s = window.__canvas.getState();
        s.updateNodeData('nTarget1', { fileKey: 'test/abc.png', url: 'https://placehold.co/120x120/1fa2dc/ffffff?text=Up' });
        return true;
    }""")
    page.wait_for_timeout(1000)
    after = page.evaluate("""() => {
        const s = window.__canvas.getState();
        const domNodes = Array.from(document.querySelectorAll('.react-flow__node')).map(el => el.getAttribute('data-id'));
        return {
            domNodeCount: domNodes.length,
            domNodes,
            hasInputBar: !!document.querySelector('.node-input-bar'),
            targetIsUploaded: !!(s.nodes.find(n=>n.id==='nTarget1')?.data?.fileKey),
        };
    }""")
    print("AFTER_UPLOAD:", after)
    browser.close()
    sys.exit(0)
