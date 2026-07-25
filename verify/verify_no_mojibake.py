"""Verify AI provider/model cards show correct Chinese (no mojibake) on :8088."""
import sys, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
PASSED = 0
FAILED = 0

def log_check(label, ok):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [PASS] {label}")
    else:
        FAILED += 1
        print(f"  [FAIL] {label}")

def login(page, email, pwd):
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    page.fill('input[placeholder*="邮箱"], input[placeholder*="email"], input[id="email"]', email)
    page.fill('input[placeholder*="密码"], input[type="password"]', pwd)
    page.keyboard.press("Enter")
    page.wait_for_selector(".pea-topnav", timeout=15000)

def open_user_menu(page):
    btn = page.locator(".pea-user-trigger")
    if btn.count() > 0:
        btn.first.click(force=True)
        page.wait_for_timeout(400)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errs = []
    page.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append(f"PAGEERROR: {e}"))

    print("=== Login as admin ===")
    login(page, "admin@pea.ai", "admin12345")
    page.wait_for_timeout(2000)

    # Navigate to Account -> AI Provider panel
    print("=== Open Account Center -> AI Provider ===")
    open_user_menu(page)
    acct = page.locator("text=账户中心")
    if acct.count() > 0:
        acct.first.click()
        page.wait_for_timeout(1000)

    # Click AI Provider tab in account
    aiprov_tab = page.locator("text=AI 提供商")
    if aiprov_tab.count() > 0:
        aiprov_tab.first.click()
        page.wait_for_timeout(1000)

    # Check for mojibake patterns in the visible text
    body_text = page.evaluate("document.body.innerText")
    print("\n=== Card text sample (first 600 chars) ===")
    print(body_text[:600])

    # Detect double-encoded UTF-8 mojibake patterns
    moji_patterns = ['Ã', 'â€', 'æœ¬', 'å›¾', 'è°ƒ', 'éŒ', 'ä½', '¥Ÿç¡€']
    found_moji = [p for p in moji_patterns if p in body_text]
    log_check("Q1: No mojibake in card descriptions", len(found_moji) == 0)
    if found_moji:
        print(f"  WARNING: Found mojibake patterns: {found_moji}")

    # Verify correct Chinese text appears
    expected_chinese = [
        "快速图像生成",
        "免费可用",
        "高质量图像生成",
        "基础套餐",
        "文生/图生视频",
        "专业套餐",
        "对话/文本生成",
        "基础参考价",
        "Tapies",
        "订阅套餐解锁更多",
    ]
    for txt in expected_chinese:
        log_check(f"  Contains '{txt}'", txt in body_text)

    # Check 4 model cards rendered
    card_count = page.locator(".pea-model-card, .pea-prov-card, [class*=card]").count()
    log_check(f"Model cards rendered ({card_count} >= 4)", card_count >= 4)

    # Console errors
    log_check("Zero console errors", len(errs) == 0)
    if errs:
        for e in errs[:10]:
            print(f"  ERR: {e}")

    # Not blank
    is_blank = page.evaluate("document.body.innerText.trim().length") < 20
    log_check("Page not blank", not is_blank)

    print(f"\n{'='*50}")
    print(f"Results: {PASSED} passed, {FAILED} failed out of {PASSED+FAILED}")
    browser.close()

sys.exit(0 if FAILED == 0 else 1)
