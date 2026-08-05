"""诊断：真实点击到底命中了什么？elementsFromPoint 全栈 + 真实点击 target 追踪。"""
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
    page.fill('input[placeholder="you@pea.ai"]', f"tneov_{ts}@pea.dev")
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
    editor.click()
    page.keyboard.press("Control+A")
    page.wait_for_timeout(150)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))
        setup(page)

        # 1) elementsFromPoint 全栈
        stack = page.evaluate("""() => {
            const btn = document.querySelector('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]');
            const r = btn.getBoundingClientRect();
            const cx = r.left + r.width/2, cy = r.top + r.height/2;
            const els = document.elementsFromPoint(cx, cy);
            return {
                rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                stack: els.map(e => (e.className||e.tagName)+'').slice(0,8)
            };
        }""")
        print("[stack] elementsFromPoint 全栈:", json.dumps(stack, ensure_ascii=False))

        # 2) 真实点击 target 追踪（document capture 探针）
        page.evaluate("""() => {
            window.__rt = [];
            document.addEventListener('mousedown', (e) => {
                const t = e.target;
                window.__rt.push((t.className||t.tagName)+'' + (t.closest('.tne-tool-btn') ? ' [inBtn]' : ''));
            }, true);
        }""")
        page.locator('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]').first.click()
        page.wait_for_timeout(300)
        rt = page.evaluate("() => window.__rt")
        print("[realclick] 真实点击 mousedown target:", json.dumps(rt, ensure_ascii=False))

        # 3) 按钮自身尺寸 & 是否真的有可点区域（对比 group）
        dims = page.evaluate("""() => {
            const btn = document.querySelector('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]');
            const grp = btn.closest('.tne-toolbar-group');
            const cs = getComputedStyle(btn);
            return {
                btnRect: (()=>{const r=btn.getBoundingClientRect();return {w:Math.round(r.width),h:Math.round(r.height),x:Math.round(r.x),y:Math.round(r.y)};})(),
                grpRect: (()=>{const r=grp.getBoundingClientRect();return {w:Math.round(r.width),h:Math.round(r.height),x:Math.round(r.x),y:Math.round(r.y)};})(),
                btnPointerEvents: cs.pointerEvents,
                btnPosition: cs.position,
                btnDisplay: cs.display,
                btnVisibility: cs.visibility,
                btnZIndex: cs.zIndex
            };
        }""")
        print("[dims] 按钮/组尺寸与样式:", json.dumps(dims, ensure_ascii=False))

        browser.close()

if __name__ == "__main__":
    main()
