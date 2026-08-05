"""假说验证：给 .tne-toolbar-group 加 pointer-events:none，按钮 auto，真实点击是否命中按钮并生成 <h1>。"""
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
    page.fill('input[placeholder="you@pea.ai"]', f"tnepe_{ts}@pea.dev")
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

        # 注入修复：group pointer-events:none, btn auto
        page.add_style_tag(content="""
            .text-node-editor-modal .tne-toolbar-group { pointer-events: none !important; }
            .text-node-editor-modal .tne-tool-btn { pointer-events: auto !important; }
        """)
        page.wait_for_timeout(200)

        # trace
        page.evaluate("""() => { window.__rt=[]; document.addEventListener('mousedown',(e)=>{const t=e.target; window.__rt.push((t.className||t.tagName)+'');},true); }""")

        editor = page.locator(".tne-editor-content")
        editor.click(); page.keyboard.press("Control+A"); page.wait_for_timeout(150)
        page.locator('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]').first.click()
        page.wait_for_timeout(400)
        rt = page.evaluate("()=>window.__rt")
        html = page.evaluate("()=>document.querySelector('.tne-editor-content').innerHTML")
        focus = page.evaluate("()=>document.activeElement===document.querySelector('.tne-editor-content')")
        print("[PE修复后 真实点击 H1] target:", json.dumps(rt, ensure_ascii=False))
        print("   -> h1?", "<h1" in html.lower(), "| 编辑区仍聚焦?", focus)
        print("   -> html:", repr(html[:80]))

        # 再测粗体
        editor.click(); page.keyboard.press("Control+A"); page.wait_for_timeout(150)
        page.locator('.text-node-editor-modal .tne-tool-btn[title*="粗体"]').first.click()
        page.wait_for_timeout(400)
        html2 = page.evaluate("()=>document.querySelector('.tne-editor-content').innerHTML")
        print("[PE修复后 真实点击 粗体] -> bold?", ("<b" in html2.lower() or "<strong" in html2.lower()), "| html:", repr(html2[:80]))

        browser.close()

if __name__ == "__main__":
    main()
