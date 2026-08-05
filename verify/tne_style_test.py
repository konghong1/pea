"""彻底 dump 按钮/span/group/toolbar 的计算样式 + 伪元素 + 同 tick elementsFromPoint。"""
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
    page.fill('input[placeholder="you@pea.ai"]', f"tnestyle_{ts}@pea.dev")
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

def dump_selector(page, sel):
    return page.evaluate("""(sel) => {
        const el = document.querySelector(sel);
        if (!el) return {sel, missing:true};
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        const before = getComputedStyle(el, '::before');
        const after = getComputedStyle(el, '::after');
        const span = el.querySelector('span');
        return {
            sel,
            rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
            pointerEvents: cs.pointerEvents,
            position: cs.position,
            zIndex: cs.zIndex,
            visibility: cs.visibility,
            display: cs.display,
            overflow: cs.overflow,
            hasSpan: !!span,
            spanPE: span ? getComputedStyle(span).pointerEvents : null,
            spanRect: span ? (()=>{const sr=span.getBoundingClientRect();return {x:Math.round(sr.x),y:Math.round(sr.y),w:Math.round(sr.width),h:Math.round(sr.height)};})() : null,
            beforeContent: before.content,
            beforePE: before.pointerEvents,
            beforePos: before.position,
            afterContent: after.content,
            afterPE: after.pointerEvents,
            afterPos: after.position
        };
    }""", sel)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))
        setup(page)

        for sel in ['.text-node-editor-modal .tne-tool-btn[title*="一级标题"]',
                    '.text-node-editor-modal .tne-toolbar-group',
                    '.text-node-editor-modal .tne-toolbar']:
            print(json.dumps(dump_selector(page, sel), ensure_ascii=False))

        # 同 tick: 取中心 + elementsFromPoint
        same = page.evaluate("""() => {
            const btn = document.querySelector('.text-node-editor-modal .tne-tool-btn[title*="一级标题"]');
            const r = btn.getBoundingClientRect();
            const cx = r.left + r.width/2, cy = r.top + r.height/2;
            const ef = document.elementFromPoint(cx, cy);
            const efs = document.elementsFromPoint(cx, cy).map(e=>(e.className||e.tagName)+'').slice(0,6);
            return { cx:Math.round(cx), cy:Math.round(cy), ef: (ef.className||ef.tagName)+'', efs };
        }""")
        print("[sametick] 中心命中:", json.dumps(same, ensure_ascii=False))
        browser.close()

if __name__ == "__main__":
    main()
