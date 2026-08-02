import uuid
from playwright.sync_api import sync_playwright

import time
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
        // 创建两个节点并打组
        store.setState({nodes:[
            {id:'nText',type:'pea',position:{x:180,y:180},data:{kind:'text',label:'text',html:'生成一只猫'}},
            {id:'nImg',type:'pea',position:{x:180,y:420},data:{kind:'image',label:'image',prompt:'',meta:{}}}
        ], edges:[], version:1, dirty:true});
        store.getState().onConnect({source:'nText', target:'nImg'});
        // 全选后打组
        store.getState().select('nText');
        store.getState().toggleSelect('nImg');
        const selIds = store.getState().selectedIds;
        store.getState().groupNodes(selIds);
        // 选中 group
        const groupId = store.getState().nodes.find(n => n.type === 'group')?.id;
        if (groupId) store.getState().select(groupId);
        window.__ui.getState().setActive('canvas');
        return {groupId, nodes: store.getState().nodes.length, edges: store.getState().edges.length};
    }""")
    print("ret:", ret)
    page.wait_for_timeout(2000)

    # 先给 group 设一个浅蓝背景，让边框在浅色画布上可见
    page.evaluate("""() => {
        const store = window.__canvas;
        const groupId = store.getState().nodes.find(n => n.type === 'group')?.id;
        if (groupId) store.getState().updateNodeData(groupId, { bgColor: 'rgba(31,162,220,0.16)' }, true);
    }""")
    page.wait_for_timeout(600)

    # 截图：group 整体
    page.screenshot(path="C:/workspace/pea/verify/shot_group_ui_fix_overview.png")

    # 截图：group 左上角圆角细节
    groupEl = page.locator('.pea-group-node').first
    box = groupEl.bounding_box()
    if box:
        page.screenshot(path="C:/workspace/pea/verify/shot_group_ui_fix_corner.png", clip={"x": box["x"], "y": box["y"], "width": 120, "height": 120})

    # 截图：切换背景按钮的色环（透明态）
    page.locator('.pgn-color-swatch').screenshot(path="C:/workspace/pea/verify/shot_group_ui_fix_swatch.png")
    page.locator('.pgn-color-btn').screenshot(path="C:/workspace/pea/verify/shot_group_ui_fix_bgbtn.png")

    # 选择蓝色背景，验证颜色环清晰可见
    page.evaluate("""() => {
        const store = window.__canvas;
        const groupId = store.getState().nodes.find(n => n.type === 'group')?.id;
        if (groupId) store.getState().updateNodeData(groupId, { bgColor: 'rgba(31,162,220,0.16)' }, true);
    }""")
    page.wait_for_timeout(600)
    page.locator('.pgn-color-swatch').screenshot(path="C:/workspace/pea/verify/shot_group_ui_fix_swatch_blue.png")
    page.locator('.pgn-color-btn').screenshot(path="C:/workspace/pea/verify/shot_group_ui_fix_bgbtn_blue.png")

    browser.close()
