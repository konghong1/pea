"""精确坐标点击 vs locator 点击：到底谁命中了 group？并统计按钮数量。"""
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
    page.fill('input[placeholder="you@pea.ai"]', f"tnecoord_{ts}@pea.dev")
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
    editor.click(); page.keyboard.press("Control+A"); page.wait_for_timeout(150)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))
        setup(page)

        # 统计 H1 按钮数量 + 各自坐标
        info = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]')];
            return btns.map(b => { const r=b.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height), vis:getComputedStyle(b).visibility}; });
        }""")
        print("[count] H1 按钮数量及坐标:", json.dumps(info, ensure_ascii=False))

        # 安装 trace
        page.evaluate("""() => { window.__rt=[]; document.addEventListener('mousedown',(e)=>{const t=e.target; window.__rt.push((t.className||t.tagName)+'');},true); }""")

        # A) 精确坐标点击按钮中心
        box = info[0]
        cx = box['x'] + box['w']//2
        cy = box['y'] + box['h']//2
        page.mouse.click(cx, cy)
        page.wait_for_timeout(300)
        print(f"[A 精确坐标 click ({cx},{cy})] target:", json.dumps(page.evaluate("()=>window.__rt"), ensure_ascii=False))
        print("    -> h1?", page.evaluate("()=>/<h1/i.test(document.querySelector('.tne-editor-content').innerHTML)"))
        page.evaluate("()=>{document.querySelector('.tne-editor-content').innerHTML='这是一段用于测试标题格式化的文本。';window.__rt=[];}")

        # B) locator 点击
        page.locator('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]').first.click()
        page.wait_for_timeout(300)
        print("[B locator click] target:", json.dumps(page.evaluate("()=>window.__rt"), ensure_ascii=False))
        print("    -> h1?", page.evaluate("()=>/<h1/i.test(document.querySelector('.tne-editor-content').innerHTML)"))

        browser.close()

if __name__ == "__main__":
    main()
