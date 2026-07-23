"""Debug: 检查节点位置 + handle 位置 + 模拟拖动"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("C:/workspace/pea/verify/shots")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(800)
    ts = int(time.time() * 1000)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', f"dbg_{ts}@pea.ai")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "Dbg")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    page.wait_for_timeout(800)

    def add(kind):
        page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        label = {"text":"文本","image":"图片","video":"视频","audio":"音频"}[kind]
        items = page.locator(".pea-add-menu-item").all()
        for it in items:
            if label in (it.text_content() or ""):
                box = it.bounding_box()
                page.mouse.click(box["x"]+box["width"]/2, box["y"]+box["height"]/2)
                page.wait_for_timeout(500)
                return

    add("text")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    add("image")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    info = page.evaluate("""() => {
        const nodes = Array.from(document.querySelectorAll('.react-flow__node'));
        return nodes.map(n => {
            const r = n.getBoundingClientRect();
            const id = n.getAttribute('data-id');
            const handles = Array.from(n.querySelectorAll('.react-flow__handle')).map(h => {
                const hr = h.getBoundingClientRect();
                return {
                    pos: h.getAttribute('data-handlepos'),
                    type: h.getAttribute('data-handletype'),
                    x: hr.x + hr.width/2, y: hr.y + hr.height/2,
                    w: hr.width, h: hr.height
                };
            });
            return { id, kind: n.getAttribute('data-kind'), rect: r, handles };
        });
    }""")
    print("NODES:")
    for n in info:
        print(f"  id={n['id']} kind={n['kind']} rect={n['rect']}")
        for h in n['handles']:
            print(f"    handle pos={h['pos']} type={h['type']} center=({h['x']:.1f},{h['y']:.1f}) size={h['w']}x{h['h']}")

    page.screenshot(path=str(OUT / "_dbg_two_nodes.png"))
    browser.close()