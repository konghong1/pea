from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
    page = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    page.on("pageerror", lambda e: errs.append(f"PAGEERR: {e}"))
    page.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type in ("error","warning") else None)

    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(800)
    page.screenshot(path=str(SHOTS/"diag_landing.png"))
    print("URL after load:", page.url)
    print("has register btn:", page.get_by_role("button", name="没有账号？去注册").count())
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(400)
    ts = int(time.time())
    page.fill('input[placeholder="you@pea.ai"]', f"dl_{ts}@pea.dev")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "DL")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    page.screenshot(path=str(SHOTS/"diag_after_reg.png"))
    print("URL after reg:", page.url)
    for sel in [".react-flow__viewport", ".react-flow", ".pea-workspace", ".pea-canvas", "canvas", "[class*='workspace']", "[class*='canvas']"]:
        try:
            print(f"  {sel}: {page.locator(sel).count()}")
        except Exception as e:
            print(f"  {sel}: ERR {e}")
    print("ERRORS:", errs[:15])
    b.close()
