"""深挖 v2（健壮 setup）：截图 + 按钮中心完整命中栈 + 按钮完整计算样式。"""
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
        page.wait_for_timeout(800)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"tnedeep2_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "TNE")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(6000)
        # 健壮：等待 canvas 或 新建项目
        try:
            page.locator("button", has_text="新建项目").first.wait_for(timeout=8000)
            page.locator("button", has_text="新建项目").first.click()
        except Exception:
            print("[setup] 未找到 新建项目，尝试直接等 canvas / 截图")
            page.screenshot(path=str(SHOTS/"deep_setup.png"))
        page.wait_for_timeout(2000)
        try:
            page.wait_for_selector(".react-flow__viewport", timeout=15000)
        except Exception as e:
            print("[setup] 无 canvas:", e); page.screenshot(path=str(SHOTS/"deep_nocanvas.png")); browser.close(); return

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

        page.screenshot(path=str(SHOTS/"deep_modal.png"))
        print("[shot] deep_modal.png saved")

        info = page.evaluate("""() => {
            const b = document.querySelector('.tne-tool-btn[title*="一级标题"]');
            const r = b.getBoundingClientRect();
            const cx = r.x + r.width/2, cy = r.y + r.height/2;
            const stack = document.elementsFromPoint(cx, cy).map(el => (el.className&&el.className.toString().slice(0,30))+'|'+el.tagName+'|pe='+getComputedStyle(el).pointerEvents);
            const cs = getComputedStyle(b);
            return {
              rect:{x:r.x,y:r.y,w:r.width,h:r.height,cx,cy},
              stack,
              btnStyle:{ w:cs.width, h:cs.height, disp:cs.display, vis:cs.visibility, op:cs.opacity, pe:cs.pointerEvents, position:cs.position, z:cs.zIndex, bs:cs.boxSizing },
            };
        }""")
        print("[deep] rect:", json.dumps(info['rect'], ensure_ascii=False))
        print("[deep] elementsFromPoint stack (top→bottom):", json.dumps(info['stack'], ensure_ascii=False))
        print("[deep] btn computed style:", json.dumps(info['btnStyle'], ensure_ascii=False))

        browser.close()

if __name__ == "__main__":
    main()
