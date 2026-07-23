from playwright.sync_api import sync_playwright
import time, sys

OUT = "C:/workspace/pea/verify/shots/uir4_current_text_node.png"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errs = []
    page.on("console", lambda m: m.type == "error" and errs.append(m.text))
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(1500)
    ts = int(time.time() * 1000)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(500)
    page.fill('input[placeholder="you@pea.ai"]', f"v4_{ts}@pea.dev")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "V4")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(6000)
    print("viewport count:", page.locator(".react-flow__viewport").count())
    if page.locator(".react-flow__viewport").count() == 0:
        page.screenshot(path="C:/workspace/pea/verify/shots/_debug_still_login.png")
        print("still on login page")
        sys.exit(1)
    page.wait_for_timeout(800)
    # 触发菜单
    page.evaluate("() => document.querySelector('.pea-tlb-btn[aria-label*=\"添加节点\"]').click()")
    page.wait_for_selector(".pea-add-menu", timeout=4000)
    # 选文本
    items = page.locator(".pea-add-menu-item").all()
    for it in items:
        if "文本" in (it.text_content() or ""):
            box = it.bounding_box()
            page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            break
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    # 选中文字节点并输入一些字以触发 FloatingTextToolbar
    n = page.locator('.pea-node[data-kind="text"]').first
    n.click()
    page.wait_for_timeout(500)
    # 截图
    page.screenshot(path=OUT)
    print("[ok] screenshot saved")
    print("console errors:", len(errs))
    browser.close()