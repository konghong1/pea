from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("requestfailed", lambda r: print("REQ FAILED:", r.method, r.url, r.failure))
    page.on("response", lambda r: print("RESP", r.status, r.url) if "/api" in r.url or "/register" in r.url or "/login" in r.url else None)
    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(800)
    ts = int(time.time() * 1000)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', f"v4debug{ts}@pea.ai")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    print("toast text:", page.locator(".ant-message").text_content() or "none")
    print("url:", page.url)
    print("viewport count:", page.locator(".react-flow__viewport").count())
    browser.close()