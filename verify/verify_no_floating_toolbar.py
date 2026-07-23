from playwright.sync_api import sync_playwright
import time

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
    page.fill('input[placeholder="you@pea.ai"]', f"v4b_{ts}@pea.dev")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "V4b")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(6000)
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
    # 选中文字节点
    n = page.locator('.pea-node[data-kind="text"]').first
    n.click()
    page.wait_for_timeout(500)
    # 1) 文本节点 + FloatingTextToolbar 已移除 + node-input-bar 仍在
    page.screenshot(path="C:/workspace/pea/verify/shots/uir4_after_text_no_toolbar.png")
    # 2) 验证 FloatingTextToolbar 不存在
    toolbar_count = page.locator(".text-node-toolbar").count()
    print(f"text-node-toolbar count: {toolbar_count} (expect 0)")
    # 3) 验证 node-input-bar 仍在
    inputbar_count = page.locator(".node-input-bar").count()
    print(f"node-input-bar count: {inputbar_count} (expect 1)")
    # 4) 在输入框中输入文字
    ta = page.locator(".node-input-textarea").first
    if ta.count() > 0:
        ta.fill("你好 pea")
        page.wait_for_timeout(300)
        page.screenshot(path="C:/workspace/pea/verify/shots/uir4_text_with_typing.png")
    # 5) Escape 取消选中
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.screenshot(path="C:/workspace/pea/verify/shots/uir4_text_deselected.png")
    print(f"console errors: {len(errs)}")
    if errs:
        for e in errs: print("  ERR:", e)
    browser.close()