import uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: print(f"[console:{m.type}] {m.text}"))
    page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    page.locator("text=没有账号？去注册").first.click()
    page.wait_for_timeout(400)
    email = f"dbg_{uuid.uuid4().hex[:8]}@pea.ai"
    page.fill('input[placeholder="you@pea.ai"]', email)
    page.fill('input[placeholder="至少 8 位"]', "test1234")
    page.fill('input[placeholder="可选"]', "Dbg")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(2000)
    page.wait_for_selector("text=新建项目", timeout=15000)

    cid = page.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'dbg',scope:'personal'})});
        return (await r.json()).id;
    }""")
    print("cid:", cid)

    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    ret = page.evaluate(f"""async () => {{
        console.log('typeof __canvas', typeof window.__canvas, 'getState' in window.__canvas);
        const store = window.__canvas;
        console.log('state0', store.getState().nodes.length);
        await store.getState().openCanvas({cid});
        console.log('state1', store.getState().nodes.length);
        store.setState({{nodes:[
            {{id:'nText',type:'pea',position:{{x:150,y:150}},data:{{kind:'text',label:'text',html:'生成一只猫'}}}},
            {{id:'nImg',type:'pea',position:{{x:150,y:400}},data:{{kind:'image',label:'image',prompt:'',meta:{{}}}}}}
        ], edges:[], version:1, dirty:true}});
        console.log('state2 after setState', store.getState().nodes.length);
        store.getState().onConnect({{source:'nText', target:'nImg'}});
        console.log('state3', store.getState().nodes.length, store.getState().edges.length);
        store.getState().select('nImg');
        window.__ui.getState().setActive('canvas');
        console.log('state4', store.getState().selectedId);
        return {{nodes: store.getState().nodes.length, edges: store.getState().edges.length, selectedId: store.getState().selectedId}};
    }}""")
    print("ret:", ret)
    page.wait_for_timeout(2000)
    nodes = page.locator(".react-flow__node").count()
    print("rendered nodes:", nodes)
    page.screenshot(path="C:/workspace/pea/verify/_debug_canvas_shot.png")
    browser.close()
