from playwright.sync_api import sync_playwright
import time, sys

BASE = "http://localhost:8088"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errs = []
    page.on("console", lambda m: m.type == "error" and errs.append(m.text))
    page.on("pageerror", lambda e: errs.append(str(e)))

    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    ts = int(time.time() * 1000)
    email = f"rf_{ts}@pea.ai"
    # 注册
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(500)
    page.fill('input[placeholder="you@pea.ai"]', email)
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(8000)

    tok_after_login = page.evaluate("() => localStorage.getItem('pea_token')")
    url_after_login = page.url
    print("URL after login :", url_after_login)
    print("token after login:", (tok_after_login[:24] + "...") if tok_after_login else None)
    print("has react-flow   :", page.locator(".react-flow__viewport").count())

    # ===== 关键：硬刷新（强刷）=====
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    tok_after_reload = page.evaluate("() => localStorage.getItem('pea_token')")
    url_after_reload = page.url
    print("--- after HARD reload ---")
    print("URL after reload :", url_after_reload)
    print("token after reload:", (tok_after_reload[:24] + "...") if tok_after_reload else None)
    print("token survived?  :", bool(tok_after_login and tok_after_reload and tok_after_login == tok_after_reload))
    print("bounced to login?:", url_after_reload.endswith("/login") or "/login" in url_after_reload)
    print("has react-flow   :", page.locator(".react-flow__viewport").count())
    print("console errors   :", errs[:5])
    browser.close()
