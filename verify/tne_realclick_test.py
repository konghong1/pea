"""真实点击矩阵：全选 vs 光标，验证 H1 是否生效 + 焦点/闪动。"""
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
    page.fill('input[placeholder="you@pea.ai"]', f"tnereal_{ts}@pea.dev")
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
    editor.click()
    page.wait_for_timeout(200)
    page.keyboard.type("这是一段用于测试标题格式化的文本。", delay=20)
    page.wait_for_timeout(300)

def focus_trace_install(page):
    page.evaluate("""() => {
        window.__ft = [];
        const ed = document.querySelector('.tne-editor-content');
        const btn = document.querySelector('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]');
        ed.addEventListener('focus', () => window.__ft.push('ed:focus'));
        ed.addEventListener('blur', () => window.__ft.push('ed:blur'));
        btn.addEventListener('mousedown', () => window.__ft.push('btn:mousedown-native'), true);
        // 计数 React onMouseDown 是否触发：用 MutationObserver 监听 editor 内容变化
        window.__h1count = 0;
        const mo = new MutationObserver(() => { if (/<h1/i.test(ed.innerHTML)) window.__h1count++; });
        mo.observe(ed, {childList:true, subtree:true, characterData:true});
    }""")

def get_trace(page):
    return page.evaluate("() => ({ ft: window.__ft, h1count: window.__h1count, activeIsEditor: document.activeElement === document.querySelector('.tne-editor-content'), html: document.querySelector('.tne-editor-content').innerHTML.slice(0,50) })")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))
        setup(page)
        focus_trace_install(page)

        # 场景1：全选后点 H1（真实点击）
        editor = page.locator(".tne-editor-content")
        editor.click()
        page.keyboard.press("Control+A")
        page.wait_for_timeout(150)
        page.locator('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]').first.click()
        page.wait_for_timeout(400)
        r1 = get_trace(page)
        print("[场景1 全选+H1] ", json.dumps(r1, ensure_ascii=False))
        page.evaluate("() => { document.querySelector('.tne-editor-content').innerHTML='这是一段用于测试标题格式化的文本。'; }")
        page.wait_for_timeout(200)
        page.evaluate("() => { window.__ft=[]; window.__h1count=0; }")

        # 场景2：仅光标（不选中）点 H1
        editor.click()
        page.keyboard.press("End")
        page.wait_for_timeout(150)
        page.locator('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]').first.click()
        page.wait_for_timeout(400)
        r2 = get_trace(page)
        print("[场景2 光标+H1] ", json.dumps(r2, ensure_ascii=False))

        browser.close()

if __name__ == "__main__":
    main()
