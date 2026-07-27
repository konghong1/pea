import os, sys, uuid, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5174"
EMAIL = f"up_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
HERE = os.path.dirname(os.path.abspath(__file__))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    ctx = browser.new_context(viewport={"width":1440,"height":900})
    page = ctx.new_page()
    logs = []
    page.on("console", lambda m: logs.append(f"[console:{m.type}] {m.text}"))
    page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))

    # 模拟 BFF /files/upload 返回 500（非 401，不触发踢登录）
    page.route("**/files/upload", lambda route: route.fulfill(
        status=500, content_type="application/json", body=json.dumps({"message":"simulated bff failure"})))

    def inject(cid):
        page.evaluate(f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))")
        page.wait_for_selector(".react-flow__viewport", timeout=20000)
        page.wait_for_timeout(800)

    def load_graph():
        page.evaluate("""() => {
            const store = window.__canvas.getState();
            const mk=(id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
            const nGen=mk('nGen','image',120,160,{resultUrl:'https://placehold.co/120x120/1fa2dc/fff?text=AI',resultUrls:['https://placehold.co/120x120/1fa2dc/fff?text=AI'],prompt:'cat',meta:{}});
            const nEmpty=mk('nEmpty','image',420,160,{prompt:'',meta:{}});
            store.loadGraph([nGen,nEmpty],[],store.version);
            return true;
        }""")
        page.wait_for_timeout(1200)

    def state_of(nid):
        return page.evaluate(f"""() => {{
            const s=window.__canvas.getState();
            const n=s.nodes.find(x=>x.id==='{nid}');
            return {{
                sel:s.selectedId,
                kind:n?.data.kind, fileKey:n?.data.fileKey||null, url:n?.data.url||null,
                resultUrl:n?.data.resultUrl||null, resultUrls:(n?.data.resultUrls||[]).length,
                hasEditor: !!document.querySelector('.node-prompt-editor'),
                isUploaded: !!(n && (n.data.kind==='image'||n.data.kind==='video') && !!(n.data.fileKey||n.data.url) && !(n.data.resultUrl||(n.data.resultUrls&&n.data.resultUrls.length)))
            }};
        }}""")

    def on_login_page():
        return page.evaluate("() => location.pathname === '/login'")

    # ---- login + canvas ----
    page.goto(BASE, wait_until="networkidle"); page.wait_for_timeout(600)
    page.get_by_role("button", name="没有账号？去注册").first.click(); page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "UpBot")
    page.locator("form button[type=submit]").click(); page.wait_for_timeout(4000)
    cid = page.evaluate("""async () => {
        const token=localStorage.getItem('pea_token');
        const r=await fetch('/canvases',{method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'up',scope:'personal'})});
        return (await r.json()).id;
    }""")
    print("canvas id:", cid)
    inject(cid)

    print("\n========== (A) 有效 token：AI 节点上传成功（阻断 500 拦截先） ==========")
    page.unroute("**/files/upload")
    load_graph()
    page.evaluate("window.__canvas.getState().select('nGen')"); page.wait_for_timeout(300)
    page.locator('.react-flow__node[data-id="nGen"] input[type=file]').set_input_files(os.path.join(HERE,'t1.png'))
    page.wait_for_timeout(2500)
    stA = state_of('nGen')
    print("  after success:", json.dumps(stA, ensure_ascii=False))
    ok_A = bool(stA['fileKey'] and not stA['resultUrl'] and stA['isUploaded'] and not stA['hasEditor'])
    print("  PASS(A) 成功路径未破坏:", ok_A)

    # 重新挂 500 拦截
    page.route("**/files/upload", lambda route: route.fulfill(
        status=500, content_type="application/json", body=json.dumps({"message":"simulated bff failure"})))

    print("\n========== (B) 模拟上传失败(500)：AI 节点绝不被破坏 ==========")
    load_graph()
    page.evaluate("window.__canvas.getState().select('nGen')"); page.wait_for_timeout(300)
    before = state_of('nGen'); print("  before fail:", json.dumps(before, ensure_ascii=False))
    page.locator('.react-flow__node[data-id="nGen"] input[type=file]').set_input_files(os.path.join(HERE,'t2.png'))
    page.wait_for_timeout(2500)
    stB = state_of('nGen')
    print("  after fail :", json.dumps(stB, ensure_ascii=False))
    print("  on_login_page:", on_login_page())
    ok_B = bool(stB['resultUrl'] and not stB['isUploaded'] and stB['hasEditor'] and not on_login_page())
    print("  PASS(B) 失败保留 resultUrl+编辑框、不被踢登录:", ok_B)

    print("\n========== (C) 模拟上传失败(500)：空上传节点不崩溃 ==========")
    page.evaluate("window.__canvas.getState().select('nEmpty')"); page.wait_for_timeout(300)
    page.locator('.react-flow__node[data-id="nEmpty"] input[type=file]').set_input_files(os.path.join(HERE,'t1.png'))
    page.wait_for_timeout(2500)
    stC = state_of('nEmpty')
    print("  empty after fail:", json.dumps(stC, ensure_ascii=False))
    ok_C = (not stC['fileKey']) and (not on_login_page())
    print("  PASS(C) 空节点失败无异常、不踢登录:", ok_C)

    print("\n===== 非上传相关 console 错误 =====")
    for l in logs:
        if ('console:error' in l or 'pageerror' in l) and 'files/upload' not in l:
            print("  ", l)

    print("\n===== RESULT =====")
    print("  A success-path-ok:", ok_A)
    print("  B fail-keeps-AI :", ok_B)
    print("  C empty-fail-ok :", ok_C)
    print("  ALL PASS:", ok_A and ok_B and ok_C)
    browser.close()
    sys.exit(0 if (ok_A and ok_B and ok_C) else 1)
