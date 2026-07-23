"""Debug: handle 拖动顺序"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("C:/workspace/pea/verify/shots")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: m.type=="error" and print(f"CONSOLE: {m.text[:200]}"))
    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(800)
    ts = int(time.time() * 1000)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', f"dbg2_{ts}@pea.ai")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "Dbg2")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    page.wait_for_timeout(1500)

    def add(kind):
        page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        label = {"text":"文本","image":"图片","video":"视频","audio":"音频"}[kind]
        for it in page.locator(".pea-add-menu-item").all():
            if label in (it.text_content() or ""):
                box = it.bounding_box()
                page.mouse.click(box["x"]+box["width"]/2, box["y"]+box["height"]/2)
                page.wait_for_timeout(600)
                page.mouse.move(10, 10)
                page.wait_for_timeout(300)
                return

    add("text")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    add("image")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    info = page.evaluate("""() => {
        const nodes = Array.from(document.querySelectorAll('.react-flow__node'));
        return nodes.map(n => {
            const r = n.getBoundingClientRect();
            return { id: n.getAttribute('data-id'), kind: n.querySelector('.pea-node')?.getAttribute('data-kind'),
                     x: r.x, y: r.y, w: r.width, h: r.height };
        });
    }""")
    print("NODES (after add text + image):")
    for n in info:
        print(f"  {n}")

    # 试拖拽：nodes[0] 的 right -> nodes[1] 的 left
    nodes = page.locator(".react-flow__node").all()
    src = nodes[0].locator('.react-flow__handle[data-handlepos="right"]').first
    tgt = nodes[1].locator('.react-flow__handle[data-handlepos="left"]').first
    sb = src.bounding_box()
    tb = tgt.bounding_box()
    print(f"\n[drag] src right ({nodes[0].get_attribute('data-id')}): {sb}")
    print(f"[drag] tgt left  ({nodes[1].get_attribute('data-id')}): {tb}")

    # 先看 src 是否真的可以拖
    print("\n[debug] check src element:", src.evaluate("el => ({ tag: el.tagName, cls: el.className, html: el.outerHTML.slice(0, 200) })"))

    # 拖拽：使用 hover + 真实的 mouse 序列
    page.mouse.move(sb["x"] + sb["width"]/2, sb["y"] + sb["height"]/2)
    page.mouse.down()
    # 慢速移动，让 ReactFlow 跟上
    steps = 30
    sx, sy = sb["x"] + sb["width"]/2, sb["y"] + sb["height"]/2
    tx, ty = tb["x"] + tb["width"]/2, tb["y"] + tb["height"]/2
    for i in range(1, steps+1):
        ix = sx + (tx - sx) * i / steps
        iy = sy + (ty - sy) * i / steps
        page.mouse.move(ix, iy)
        page.wait_for_timeout(30)
    # 看看 hover 状态时 handle 是什么样
    page.wait_for_timeout(200)
    state = page.evaluate("""() => {
        const nodes = document.querySelectorAll('.react-flow__node');
        return Array.from(nodes).map(n => ({
            id: n.getAttribute('data-id'),
            className: n.className,
        }));
    }""")
    print("\n[debug] node classes during drag:", state)
    # 看 connection line 是否出现
    conn = page.evaluate("""() => {
        const c = document.querySelector('.react-flow__connection');
        return c ? { tag: c.tagName, d: c.querySelector('path')?.getAttribute('d')?.slice(0, 100) } : null;
    }""")
    print(f"[debug] connection path: {conn}")
    page.mouse.up()
    page.wait_for_timeout(800)

    edge_cnt = page.locator(".react-flow__edge").count()
    print(f"\n[result] edge count = {edge_cnt}")
    page.screenshot(path=str(OUT / "_dbg_after_drag.png"))
    browser.close()