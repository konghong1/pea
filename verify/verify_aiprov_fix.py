import os, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
EMAIL, PW = "admin@pea.ai", "admin12345"
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 登录
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(600)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(2500)
    print("[login] done")

    # 路径1：管理员控制台 -> AI 提供商 tab
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(400)
    page.get_by_text("管理员控制台").click()
    page.wait_for_timeout(2500)
    body = page.locator("body").inner_text()
    blank = len(body.strip()) < 20
    tabs = page.locator(".ant-tabs-tab").count()
    rows = page.locator(".ant-table-tbody tr.ant-table-row").count()
    print(f"[admin console] blank={blank} tabs={tabs} providerRows={rows}")
    admin_ok = (not blank) and tabs >= 3 and rows > 0

    # 路径2：账户中心 -> AI 提供商 面板
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(400)
    page.get_by_text("账户中心").click()
    page.wait_for_timeout(1500)
    page.locator('[data-pane="aiprov"]').click()
    page.wait_for_timeout(1800)
    cards = page.locator(".pea-card-grid .pea-card").count()
    head = page.locator(".acct-pane-title").inner_text()
    print(f"[aiprov pane] cards={cards} title={head!r}")
    aiprov_ok = cards > 0

    browser.close()

print(f"\nconsole errors ({len(errors)}):")
for e in errors:
    print("  ", e[:200])
print(f"\nRESULT: admin_console={'PASS' if admin_ok else 'FAIL'}  aiprov_pane={'PASS' if aiprov_ok else 'FAIL'}  no_console_error={'PASS' if len(errors)==0 else 'FAIL'}")
sys.exit(0 if (admin_ok and aiprov_ok and len(errors)==0) else 1)
