import os, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"e13_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []
passes, fails = 0, 0

def shot(page, name):
    p = os.path.join(SHOTS, f"e13_{name}.png")
    page.screenshot(path=p)
    return p

def check(label, ok):
    global passes, fails
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if ok:
        passes += 1
    else:
        fails += 1

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册（唯一邮箱避免画布/账户状态污染）
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "E13Bot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)

    # 2) 进入账户中心
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(500)
    page.get_by_text("账户中心", exact=True).click()
    page.wait_for_selector(".acct-layout", timeout=10000)
    page.wait_for_timeout(600)
    shot(page, "01_account_center")

    # 3) 页头：Tapies 余额 + 默认资料面板含「积分流水」预览
    has_tapies = page.get_by_text("Tapies").count() > 0
    check("页头显示 Tapies 余额", has_tapies)
    has_ledger_preview = page.get_by_text("积分流水", exact=False).count() > 0
    check("默认资料面板含「积分流水」预览", has_ledger_preview)

    # 4) 7 项导航齐全
    NAVS = ["资料设置", "通用设置", "AI 提供商", "权益和账单", "邀请好友", "我的通知", "帮助与支持"]
    side = page.locator(".acct-side")
    for n in NAVS:
        cnt = side.locator(".acct-nav").filter(has_text=n).count()
        check(f"左导航存在「{n}」", cnt > 0)
    check("左导航共 7 项", side.locator(".acct-nav").count() == 7)

    # 5) 逐个面板切换 + 标题校验
    PANES = {
        "资料设置": "资料设置",
        "通用设置": "通用设置",
        "AI 提供商": "限制项目 AI 提供商配置",
        "权益和账单": "权益和账单",
        "邀请好友": "邀请好友",
        "我的通知": "我的通知",
        "帮助与支持": "帮助与支持",
    }
    for nav_label, title in PANES.items():
        side.locator(".acct-nav").filter(has_text=nav_label).click()
        page.wait_for_timeout(500)
        title_ok = page.locator(".acct-pane.active .acct-pane-title").inner_text().strip() == title
        check(f"切换到「{nav_label}」→ 标题「{title}」", title_ok)
        shot(page, f"pane_{nav_label}")

    # 6) AI 提供商面板：Provider 卡片 + 开关 + 设为默认
    side.locator(".acct-nav").filter(has_text="AI 提供商").click()
    page.wait_for_selector(".acct-content div.pea-card", timeout=8000)
    page.wait_for_timeout(400)
    cards = page.locator(".acct-content div.pea-card").count()
    check(f"AI 提供商卡片数 = {cards} (>=2)", cards >= 2)
    sw = page.locator(".acct-content .ant-switch").first
    before = sw.get_attribute("aria-checked")
    sw.click()
    page.wait_for_timeout(400)
    after = sw.get_attribute("aria-checked")
    check("Provider 开关可切换", before != after)

    # 7) 权益和账单：完整积分流水表
    side.locator(".acct-nav").filter(has_text="权益和账单").click()
    page.wait_for_timeout(500)
    has_full_ledger = page.locator(".acct-pane.active", has_text="积分流水").count() > 0
    check("权益和账单含「积分流水」", has_full_ledger)

    # 8) 我的通知：开关可切换 + 保存
    side.locator(".acct-nav").filter(has_text="我的通知").click()
    page.wait_for_timeout(400)
    notif_sw = page.locator(".acct-content .ant-switch").first
    nb = notif_sw.get_attribute("aria-checked")
    notif_sw.click()
    page.wait_for_timeout(300)
    na = notif_sw.get_attribute("aria-checked")
    check("通知开关可切换", nb != na)
    page.get_by_role("button", name="保存通知偏好").click()
    page.wait_for_timeout(400)

    # 9) 深色主题
    page.get_by_text("深", exact=True).first.click()
    page.wait_for_timeout(500)
    is_dark = "dark" in (page.evaluate("document.documentElement.className") or "")
    check("深色主题生效", is_dark)
    shot(page, "09_dark")

    # 汇总
    print(f"\n=== PASS={passes} FAIL={fails} ===")
    print("=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:30]:
            print(" ", e)
    else:
        print("  (none)")
    print(f"\nTOTAL console errors: {len(errors)}")
    browser.close()
