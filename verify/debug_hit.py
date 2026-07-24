"""诊断：在 source handle 的视觉中心坐标处，elementFromPoint 实际命中的是哪个元素？"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"hit_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "HIT")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.mouse.dblclick(300, 260); page.wait_for_timeout(350)
        page.locator(".pea-add-menu-item", has_text="文本").first.click(); page.wait_for_timeout(600)
        page.mouse.dblclick(1080, 260); page.wait_for_timeout(350)
        page.locator(".pea-add-menu-item", has_text="图片").first.click(); page.wait_for_timeout(800)

        nodes = page.locator(".react-flow__node")
        tb = nodes.nth(0).bounding_box()
        page.mouse.click(tb["x"] + tb["width"]/2, tb["y"] + tb["height"]*0.62)
        page.wait_for_timeout(300)

        info = page.evaluate("""() => {
            const node = document.querySelectorAll('.react-flow__node')[0];
            const handle = node.querySelector('.react-flow__handle.source');
            if (!handle) return {err: 'no source handle'};
            const r = handle.getBoundingClientRect();
            const cx = r.x + r.width/2, cy = r.y + r.height/2;
            const top = document.elementFromPoint(cx, cy);
            function desc(el){
                if(!el) return null;
                return {
                    tag: el.tagName,
                    cls: el.className && el.className.toString ? el.className.toString() : el.className,
                    isHandle: el.classList && el.classList.contains('react-flow__handle'),
                    pe: getComputedStyle(el).pointerEvents,
                    inHandle: !!el.closest('.react-flow__handle'),
                };
            }
            return {
                handleRect: {x:r.x,y:r.y,w:r.width,h:r.height,cx,cy},
                handlePE: getComputedStyle(handle).pointerEvents,
                handleStyle: handle.getAttribute('style'),
                topAtHandleCenter: desc(top),
            };
        }""")
        print("DIAG:", info)
        b.close()

if __name__ == "__main__":
    main()
