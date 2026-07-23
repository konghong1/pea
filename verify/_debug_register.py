"""Debug: 注册后页面状态"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("C:/workspace/pea/verify/shots")
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: print(f"CONSOLE[{m.type}]: {m.text[:200]}"))
    page.on("pageerror", lambda e: print(f"PAGEERROR: {e}"))
    page.on("response", lambda r: print(f"HTTP {r.status}: {r.url[:120]}") if r.status >= 400 else None)

    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(800)
    ts = int(time.time() * 1000)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', f"zc_dbg_{ts}@pea.ai")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(8000)
    page.screenshot(path=str(OUT / "_dbg_after_register.png"))
    print("URL:", page.url)
    body = page.evaluate("() => document.body.innerText.slice(0, 500)")
    print("BODY:", body)
    browser.close()