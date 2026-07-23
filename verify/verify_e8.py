import os, json, urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
API = "http://localhost:4100"  # bff 宿主端口（容器内 4000，宿主映射 4100）
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL, PW = "verify@pea.ai", "password123"
errors = []

def shot(page, name):
    p = os.path.join(SHOTS, f"e8_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")
    return p

def api(method, path, token=None, body=None):
    req = urllib.request.Request(API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

# 将 Provider 状态重置为已知基线: mock-video 启用, mock-image 为默认
try:
    tok = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})["token"]
    api("PATCH", "/providers/mock-video", tok, {"enabled": True})
    api("PATCH", "/providers/mock-image", tok, {"isDefault": True})
    print("[reset] provider baseline set")
except Exception as e:
    print("[reset][WARN]", e)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 登录
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(2500)

    # 2) 主页 Workspace (T-M3-01)
    page.get_by_text("主页", exact=True).first.click()
    page.wait_for_timeout(900)
    home_ok = page.get_by_text("最近项目").count() > 0
    proj_cards = page.locator("div.pea-card").filter(has_text="节点").count()
    print(f"[check] 主页「最近项目」可见: {home_ok}; 项目卡片数: {proj_cards}")
    shot(page, "01_home")

    # 3) 设置 · AI Provider (T-G-06 / T-M5-02) — 原型: 设置入口在头像菜单
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(500)
    page.get_by_text("AI Provider 设置").click()
    page.wait_for_timeout(1200)
    # 等待加载完成（Spin 消失或卡片出现）
    try:
        page.wait_for_selector("div.pea-card", timeout=8000)
    except Exception:
        pass
    cards = page.locator("div.pea-card").count()
    print(f"[check] 设置页 Provider 卡片数: {cards}")
    shot(page, "02_settings")

    # 关闭 mock-video
    sw = page.get_by_label("启用 Mock 视频生成")
    was_on = sw.is_checked()
    sw.click()
    page.wait_for_timeout(500)
    off_now = not sw.is_checked()
    print(f"[check] 关闭 Mock 视频生成: was_on={was_on} -> off={off_now}")

    # 将 Seedance 设为默认
    seed = page.locator("div.pea-card").filter(has_text="Seedance 2.0")
    seed.get_by_role("button", name="设为默认").click()
    page.wait_for_timeout(500)
    seed_default = seed.get_by_text("默认", exact=True).count() > 0
    print(f"[check] Seedance 设为默认生效: {seed_default}")
    shot(page, "03_settings_toggled")

    # 4) 持久化: 刷新后重新进入设置
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(500)
    page.get_by_text("AI Provider 设置").click()
    page.wait_for_timeout(900)
    sw2 = page.get_by_label("启用 Mock 视频生成")
    persisted_off = not sw2.is_checked()
    seed2 = page.locator("div.pea-card").filter(has_text="Seedance 2.0")
    persisted_default = seed2.get_by_text("默认", exact=True).count() > 0
    print(f"[check] 刷新后持久化: mock-video 仍关闭={persisted_off}; seedance 仍默认={persisted_default}")
    shot(page, "04_settings_persist")

    # 5) 账户中心 (T-M5-01) — 原型: 账户入口在头像菜单
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(500)
    page.get_by_text("账户中心").click()
    page.wait_for_timeout(900)
    acc_heading = page.get_by_text("账户中心").count() > 0
    has_tapies = page.get_by_text("Tapies").count() > 0
    has_balance = page.get_by_text("积分流水").count() > 0
    print(f"[check] 账户中心: 标题={acc_heading}; Tapies={has_tapies}; 积分流水={has_balance}")
    shot(page, "05_account")

    # 汇总
    print("\n=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:30]:
            print(" ", e)
    else:
        print("  (none)")
    print(f"\nTOTAL console errors: {len(errors)}")
    browser.close()
