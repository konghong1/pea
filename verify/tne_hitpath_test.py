"""命中路径追踪：在 button/group/span 上各挂原生监听 + 记录 clientX/Y，真实点击看谁收到。"""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

def setup(page):
    page.goto("http://localhost:5173", wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    ts = int(time.time())
    page.fill('input[placeholder="you@pea.ai"]', f"tnehit_{ts}@pea.dev")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "TNE")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(4000)
    page.locator("button", has_text="新建项目").first.click()
    page.wait_for_timeout(2000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    page.locator('.pea-toolbar .pea-tlb-btn[aria-label="添加节点"]').first.click()
    page.wait_for_timeout(800)
    page.locator(".pea-add-menu-item", has_text="文本").first.click()
    page.wait_for_timeout(800)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.locator(".pea-canvas-controls").locator("button[title='适配视图 (F)']").click()
    page.wait_for_timeout(700)
    page.locator(".react-flow__node").first.dblclick()
    page.wait_for_timeout(1200)
    editor = page.locator(".tne-editor-content")
    editor.click(); page.wait_for_timeout(200)
    page.keyboard.type("这是一段用于测试标题格式化的文本。", delay=20)
    page.wait_for_timeout(300)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))
        setup(page)

        # 在 button/group/span + document 挂监听
        page.evaluate("""() => {
            window.__hp = [];
            const btn = document.querySelector('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]');
            const grp = btn.closest('.tne-toolbar-group');
            const span = btn.querySelector('span');
            const log = (who, e) => window.__hp.push(`${who}:${e.target.className||e.target.tagName}@(${Math.round(e.clientX)},${Math.round(e.clientY)})`);
            document.addEventListener('mousedown', (e)=>log('DOC',e), true);
            btn.addEventListener('mousedown', (e)=>log('BTN',e), true);
            grp.addEventListener('mousedown', (e)=>log('GRP',e), true);
            if (span) span.addEventListener('mousedown', (e)=>log('SPAN',e), true);
            // 记录按钮精确中心
            const r = btn.getBoundingClientRect();
            window.__center = {x: Math.round(r.left+r.width/2), y: Math.round(r.top+r.height/2)};
        }""")
        center = page.evaluate("()=>window.__center")
        print("[info] 按钮中心:", center)

        # 真实点击按钮中心
        page.mouse.click(center['x'], center['y'])
        page.wait_for_timeout(300)
        hp = page.evaluate("()=>window.__hp")
        print("[hitpath] 真实点击命中路径:")
        for x in hp: print("   ", x)
        html = page.evaluate("()=>document.querySelector('.tne-editor-content').innerHTML")
        print("   -> h1?", "<h1" in html.lower())

        browser.close()

if __name__ == "__main__":
    main()
