from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(600)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    ts = int(time.time())
    page.fill('input[placeholder="you@pea.ai"]', f"diag2_{ts}@pea.dev")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "D")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    print("URL after register:", page.url)
    page.screenshot(path="C:/workspace/pea/verify/shots/diag_state.png")
    btns = page.locator("button").all_inner_texts()
    print("Buttons:", [x for x in btns if x.strip()][:40])
    print("has viewport:", page.locator(".react-flow__viewport").count())
    print("has projects-page:", page.locator(".projects-page").count())
    print("has TopNav:", page.locator(".pea-topnav, nav").count())
    # 列出可见链接/卡片文本
    links = page.locator("a").all_inner_texts()
    print("Links:", [x for x in links if x.strip()][:20])
    b.close()
