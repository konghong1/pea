"""诊断连接点：computed style、class 列表、transform、位置"""
from playwright.sync_api import sync_playwright
import time, json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda e: print(f"ERR: {e}"))

    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(600)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    ts = int(time.time())
    page.fill('input[placeholder="you@pea.ai"]', f"css_{ts}@pea.dev")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "CS")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(4000)
    try:
        page.get_by_role("button", name="新建项目").first.click()
        page.wait_for_timeout(3000)
        for _ in range(5):
            if page.locator(".react-flow__viewport").count() > 0: break
            page.wait_for_timeout(1000)
    except Exception: pass
    page.wait_for_selector(".react-flow__viewport", timeout=20000)
    page.wait_for_timeout(800)

    # 创建两个节点
    def add_at(label, x, y):
        page.mouse.dblclick(x, y)
        page.wait_for_timeout(350)
        page.locator(".pea-add-menu-item", has_text=label).first.click()
        page.wait_for_timeout(600)

    add_at("文本", 360, 300)
    add_at("图片", 1040, 300)
    page.wait_for_timeout(800)
    nodes = page.locator(".react-flow__node")
    src = nodes.nth(0).locator(".react-flow__handle.source").first

    def diag(tag):
        info = page.evaluate("""([sel]) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const cs = getComputedStyle(el);
            const nodeEl = el.closest('.pea-node');
            return {
                classes: el.className,
                nodeClasses: nodeEl ? nodeEl.className : null,
                w_cs: cs.width,
                h_cs: cs.height,
                left: cs.left,
                right: cs.right,
                top: cs.top,
                transform: cs.transform,
                transformOrigin: cs.transformOrigin,
                background: cs.background,
                border: cs.border,
                filter: cs.filter,
                zIndex: cs.zIndex,
                pointerEvents: cs.pointerEvents,
                display: cs.display,
                // SVG glyph inside
                glyphCount: el.querySelectorAll('.pea-handle-glyph').length,
                rotorOpacity: (() => {
                    const r = el.querySelector('.hg-rotor'); return r ? getComputedStyle(r).opacity : null;
                })(),
            };
        }""", [".react-flow__handle.pea-handle.source"])
        # Also get bbox
        hb = src.bounding_box()
        nb = nodes.nth(0).bounding_box()
        info["_bbox_w"] = round(hb["width"],2) if hb else None
        info["_near_gap"] = round((hb["x"] if hb else 0) - ((nb["x"]+nb["width"]) if nb else 0), 2)
        print(f"\n=== {tag} ===")
        print(json.dumps(info, indent=2))
        return info

    d1 = diag("default")

    # Hover
    nodes.nth(0).hover()
    page.wait_for_timeout(500)
    d2 = diag("after_hover")

    # Zoom out slightly (2 steps)
    page.mouse.move(720, 450)
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(200)
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(300)
    d3 = diag("zoom_out_2step")

    b.close()
