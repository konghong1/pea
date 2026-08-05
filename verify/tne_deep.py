"""深挖：按钮中心的完整命中栈 + 多点点击 + 编辑器/antd按钮对照。"""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"PAGEERROR {e}"))

        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"tnedeep_{ts}@pea.dev")
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
        page.wait_for_timeout(400)
        page.locator(".pea-canvas-controls").locator("button[title='适配视图 (F)']").click()
        page.wait_for_timeout(700)
        node = page.locator(".react-flow__node").first
        node.dblclick()
        page.wait_for_timeout(1800)

        page.evaluate("""() => {
            document.addEventListener('mousedown', (e) => {
                window.__last = (e.target.className&&e.target.className.toString().slice(0,40))+'|'+e.target.tagName+'|inBtn='+(!!e.target.closest&&!!e.target.closest('.tne-tool-btn'))+'|inGroup='+(!!e.target.closest&&!!e.target.closest('.tne-toolbar-group'));
            }, true);
        }""")

        info = page.evaluate("""() => {
            const b = document.querySelector('.tne-tool-btn[title*="一级标题"]');
            const r = b.getBoundingClientRect();
            const cx = r.x + r.width/2, cy = r.y + r.height/2;
            const stack = document.elementsFromPoint(cx, cy).map(el => (el.className&&el.className.toString().slice(0,30))+'|'+el.tagName);
            // 检查 group 的伪元素
            const g = b.closest('.tne-toolbar-group');
            const before = getComputedStyle(g, '::before').content;
            const after = getComputedStyle(g, '::after').content;
            const gb = g.getBoundingClientRect();
            return { rect:{x:r.x,y:r.y,w:r.width,h:r.height,cx,cy}, stack, groupBefore:before, groupAfter:after, groupRect:{x:gb.x,y:gb.y,w:gb.width,h:gb.height} };
        }""")
        print("[deep] rect:", json.dumps(info['rect'], ensure_ascii=False))
        print("[deep] elementsFromPoint stack:", json.dumps(info['stack'], ensure_ascii=False))
        print("[deep] group ::before content:", info['groupBefore'], "| ::after:", info['groupAfter'])
        print("[deep] group rect:", json.dumps(info['groupRect'], ensure_ascii=False))

        # 多点点击
        base = info['rect']
        for dx, dy, label in [(0,0,'center'), (8,0,'+x'), (-8,0,'-x'), (0,8,'+y'), (0,-8,'-y'), (12,0,'+12x')]:
            cx = base['cx'] + dx; cy = base['cy'] + dy
            page.mouse.click(cx, cy)
            page.wait_for_timeout(120)
            last = page.evaluate("() => window.__last || 'none'")
            print(f"[click {label} @({cx:.0f},{cy:.0f})] target: {last}")
            # 复位：聚焦编辑区
            page.evaluate("""() => { const ed=document.querySelector('.tne-editor-content'); ed.focus(); const s=window.getSelection(); const r=document.createRange(); r.selectNodeContents(ed); s.removeAllRanges(); s.addRange(r); }""")

        # 对照：点击编辑器是否能聚焦/输入
        page.evaluate("() => document.querySelector('.tne-editor-content').focus()")
        page.keyboard.type("X", delay=10)
        ed_text = page.evaluate("() => document.querySelector('.tne-editor-content').innerText.slice(-5)")
        print("[对照] 编辑器可输入?", repr(ed_text))

        # 对照：antd footer OK 按钮是否收到点击（用 mousedown 记录）
        page.evaluate("() => { window.__okLast=null; const ok=document.querySelector('.ant-modal-footer button'); if(ok) ok.addEventListener('mousedown',()=>window.__okLast='OK_FIRED',true); }")
        try:
            page.locator('.ant-modal-footer button').first.click(timeout=4000)
        except Exception as e:
            print("[antd OK] click err:", str(e)[:100])
        page.wait_for_timeout(300)
        print("[对照] antd OK 按钮 mousedown:", page.evaluate("() => window.__okLast || 'none'"))

        browser.close()

if __name__ == "__main__":
    main()
