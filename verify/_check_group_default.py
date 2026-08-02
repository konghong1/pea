import uuid
import time
from playwright.sync_api import sync_playwright

BASE = "http://[::1]:5173"
BUST = f"?t={int(time.time())}"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: print(f"[console:{m.type}] {m.text}"))
    page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

    page.goto(BASE + BUST, wait_until="domcontentloaded")
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
        const r = await fetch('/api/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'dbg_group',scope:'personal'})});
        return (await r.json()).id;
    }""")
    print("cid:", cid)

    page.goto(BASE + BUST, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    ret = page.evaluate("""async () => {
        const store = window.__canvas;
        await store.getState().openCanvas(""" + str(cid) + """);
        store.setState({nodes:[
            {id:'nText',type:'pea',position:{x:180,y:180},data:{kind:'text',label:'text',html:'生成一只猫'}},
            {id:'nImg',type:'pea',position:{x:180,y:420},data:{kind:'image',label:'image',prompt:'',meta:{}}}
        ], edges:[], version:1, dirty:true});
        store.getState().onConnect({source:'nText', target:'nImg'});
        store.getState().select('nText');
        store.getState().toggleSelect('nImg');
        const selIds = store.getState().selectedIds;
        store.getState().groupNodes(selIds);
        // 不选中 group，看默认状态
        store.getState().select('__none__');
        window.__ui.getState().setActive('canvas');
        const groupId = store.getState().nodes.find(n => n.type === 'group')?.id;
        return {groupId, nodes: store.getState().nodes.length, edges: store.getState().edges.length};
    }""")
    print("ret:", ret)
    page.wait_for_timeout(2000)

    # 截图：默认未选中状态
    page.screenshot(path="C:/workspace/pea/verify/shot_group_default.png")

    # 读取 computed style
    styles = page.evaluate("""() => {
        const el = document.querySelector('.pea-group-node');
        const cs = window.getComputedStyle(el);
        const htmlBg = window.getComputedStyle(document.documentElement).backgroundColor;
        const bodyBg = window.getComputedStyle(document.body).backgroundColor;
        return {
            htmlClass: document.documentElement.className,
            bodyClass: document.body.className,
            htmlBg,
            bodyBg,
            inlineStyle: el.getAttribute('style'),
            borderColor: cs.borderColor,
            borderWidth: cs.borderWidth,
            backgroundColor: cs.backgroundColor,
            boxShadow: cs.boxShadow,
        };
    }""")
    print("default styles:", styles)

    # 选中 group
    page.evaluate("""() => {
        const store = window.__canvas;
        const groupId = store.getState().nodes.find(n => n.type === 'group')?.id;
        if (groupId) store.getState().select(groupId);
    }""")
    page.wait_for_timeout(800)
    page.screenshot(path="C:/workspace/pea/verify/shot_group_selected.png")

    styles2 = page.evaluate("""() => {
        const el = document.querySelector('.pea-group-node');
        const cs = window.getComputedStyle(el);
        return {
            borderColor: cs.borderColor,
            backgroundColor: cs.backgroundColor,
            boxShadow: cs.boxShadow,
        };
    }""")
    print("selected styles:", styles2)

    browser.close()
