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
    page.fill('input[placeholder="you@pea.ai"]', f"v4_{ts}@pea.ai")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(8000)
    # 截图登录后状态
    page.screenshot(path="C:/workspace/pea/verify/shots/_debug_after_login.png")
    print("url after login:", page.url)
    # 检查有没有渲染 react-flow
    has_viewport = page.locator(".react-flow__viewport").count()
    print("react-flow viewport count:", has_viewport)
    print("current body html snippet:", page.evaluate("() => document.body.innerHTML.slice(0, 500)"))
    print("console errors:", errs)
    browser.close()