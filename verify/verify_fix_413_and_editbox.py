"""
验证两个修复（真机 Playwright @ http://localhost:8088 生产构建）：
  A) /files/upload 大文件不再 413  -> 期望 200 且节点拿到 fileKey
  B) 点击 AI 生成的图片 -> 节点被选中 -> 下方编辑框(.node-input-bar / .node-chat-prompt)弹出

用法：python verify_fix_413_and_editbox.py
会先打印当前容器结果（修复前应为 FAIL），重建镜像后再跑一次应为 PASS。
"""
import os, sys, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
HERE = os.path.dirname(os.path.abspath(__file__))

# 生成 6MB 大文件（> nginx 默认 1m，足以触发 413）
LARGE = os.path.join(HERE, "_large_6mb.bin")
if not os.path.exists(LARGE):
    with open(LARGE, "wb") as f:
        f.write(os.urandom(6 * 1024 * 1024))

EMAIL = f"fix_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    # 8088 prod 需要 dev hooks 才暴露 window.__canvas
    page.add_init_script("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}")

    upload_statuses = []
    page.on("response", lambda r: upload_statuses.append((r.status, r.url)) if "/files/upload" in r.url else None)
    page.on("console", lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: print("[pageerror]", e))

    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    # 注册并登录
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "FixBot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(4000)

    token = page.evaluate("localStorage.getItem('pea_token')")
    cid = page.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'fix',scope:'personal'})});
        return (await r.json()).id;
    }""")
    page.evaluate(f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))")
    page.wait_for_selector(".react-flow__viewport", timeout=20000)
    page.wait_for_timeout(1500)

    # ── 测试 A: 上传 6MB 大图（修复前 nginx 1m 上限 -> 413）──
    page.evaluate("""() => {
        const store = window.__canvas.getState();
        const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
        const nUp = mk('nUp','image',150,200,{prompt:'',meta:{}});
        store.loadGraph([nUp],[], store.version);
        store.select('nUp');
        return true;
    }""")
    page.wait_for_timeout(1500)
    inp = page.locator('.react-flow__node[data-id="nUp"] input[type=file]')
    upload_statuses.clear()
    try:
        inp.set_input_files(LARGE, timeout=20000)
    except Exception as e:
        print("[warn] set_input_files error:", e)
    page.wait_for_timeout(4000)
    up_state = page.evaluate("""() => {
        const n = window.__canvas.getState().nodes.find(x=>x.id==='nUp');
        return { fileKey:n?.data?.fileKey||null, url:n?.data?.url||null };
    }""")
    passA = any(s == 200 for s, _ in upload_statuses) and bool(up_state['fileKey'])
    print("=" * 60)
    print("TEST A 上传 6MB 大图:", "PASS" if passA else "FAIL")
    print("   /files/upload 响应:", upload_statuses)
    print("   节点结果:", up_state)

    # ── 测试 B: 点击 AI 生成的图片 -> 编辑框弹出 ──
    page.evaluate("""() => {
        const store = window.__canvas.getState();
        const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
        const nGen = mk('nGen','image',150,450,{resultUrl:'https://placehold.co/200x200/1fa2dc/ffffff?text=AI',resultUrls:['https://placehold.co/200x200/1fa2dc/ffffff?text=AI'],prompt:'一只猫',meta:{}});
        store.loadGraph([nGen],[], store.version);
        store.clearSelection();
        return true;
    }""")
    page.wait_for_timeout(1500)
    # 用真实鼠标坐标点击图片中心（DOM .click() 会被 React 事件代理吞掉，必须用真实鼠标）
    img = page.locator('.react-flow__node[data-id="nGen"] img')
    box = img.bounding_box()
    page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    page.wait_for_timeout(2000)
    stB = page.evaluate("""() => {
        const s = window.__canvas.getState();
        return {
            selectedId: s.selectedId,
            hasInputBar: !!document.querySelector('.node-input-bar'),
            hasChatPrompt: !!document.querySelector('.node-chat-prompt'),
        };
    }""")
    passB = stB['selectedId'] == 'nGen' and (stB['hasInputBar'] or stB['hasChatPrompt'])
    print("TEST B 点击生成图->编辑框:", "PASS" if passB else "FAIL")
    print("   选中态/编辑框:", stB)
    print("=" * 60)
    print("RESULT:", "ALL PASS" if (passA and passB) else "HAS FAIL")

    browser.close()
    sys.exit(0)
