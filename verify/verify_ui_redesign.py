import os, time, datetime, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"uir_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []


def shot(page, name):
    p = os.path.join(SHOTS, f"uir_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")
    return p


def toolbar_btn(page, label):
    return page.locator(".pea-toolbar").get_by_role("button", name=label, exact=True).first


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 登录并进入画布
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "UIBot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    shot(page, "01_default_canvas")

    # 2) 验证聊天默认收起为圆形气泡
    bubble = page.locator(".pea-agent-bubble")
    print(f"[check] chat bubble visible: {bubble.count() > 0}")
    if bubble.count() > 0:
        bubble.first.click()
        page.wait_for_timeout(600)
        shot(page, "02_chat_expanded")
        # 关闭聊天
        page.get_by_label("收起副驾驶").first.click()
        page.wait_for_timeout(400)

    # 3) 添加生成节点后按 Escape 取消选中，验证无默认白色手柄
    toolbar_btn(page, "添加节点（双击画布也可打开）").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="生成", exact=True).first.click()
    page.wait_for_timeout(800)
    # 按 Escape 取消选中，并把鼠标移出节点避免 hover 态残留
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.mouse.move(0, 0)
    page.wait_for_timeout(300)
    shot(page, "03_node_no_handles")

    # 4) hover 节点时手柄应出现
    node = page.locator(".react-flow__node").first
    node.hover()
    page.wait_for_timeout(400)
    shot(page, "04_node_hover_handles")

    # 5) 添加文本节点并选中，验证浮动文本工具条
    toolbar_btn(page, "添加节点（双击画布也可打开）").click()
    page.wait_for_timeout(400)
    page.get_by_role("button", name="文本", exact=True).first.click()
    page.wait_for_timeout(600)
    page.locator(".react-flow__node").last.click(force=True)
    page.wait_for_timeout(500)
    shot(page, "05_text_node_toolbar")

    # 6) 验证没有底部 Composer
    composer = page.locator(".pea-composer")
    print(f"[check] bottom composer removed: {composer.count() == 0}")

    print("\n=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:30]:
            print(" ", e)
    else:
        print("  (none)")
    print(f"\nTOTAL console errors: {len(errors)}")
    browser.close()
