import os, time, datetime, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"e5_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []

def shot(page, name):
    p = os.path.join(SHOTS, f"e5_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")
    return p

def node_count(page):
    return page.locator(".react-flow__node").count()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 登录 (用 E7 已注册账号: verify@pea.ai / password123)
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.fill('input[placeholder="you@pea.ai"]', 'verify@pea.ai')
    page.fill('input[placeholder="至少 8 位"]', 'password123')
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(2500)
    shot(page, "01_workspace")

    # 2) 添加生成节点 (顶部按钮)
    # 等画布加载
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    before = node_count(page)
    # 尝试多种选择器
    added = False
    for sel in ['button[aria-label="添加生成节点"]', 'button:has-text("⚡ 生成")']:
        try:
            page.click(sel, timeout=5000)
            added = True
            break
        except Exception:
            continue
    if not added:
        print("[WARN] could not click add-node button")
    page.wait_for_timeout(800)
    after_add = node_count(page)
    print(f"[check] add generate node: {before} -> {after_add} (expect +1)")
    shot(page, "02_add_node")

    # 3) Agent 面板: 点击技能芯片 "⚡ 生成图片" -> 应再添一个生成节点
    page.get_by_text("⚡ 生成图片", exact=False).first.click()
    page.wait_for_timeout(1500)
    after_agent = node_count(page)
    print(f"[check] agent add node: {after_add} -> {after_agent} (expect +1)")
    # 验证副驾驶回复出现
    agent_has_reply = page.locator("text=已为你添加一个").count() > 0
    print(f"[check] agent reply shown: {agent_has_reply}")
    shot(page, "03_agent_panel")

    # 4) 侧边面板: 搜索/评论/历史/文件
    page.get_by_label("侧边面板").click()
    page.wait_for_timeout(600)
    shot(page, "04_sidepanel_search")
    page.get_by_text("评论", exact=True).first.click()
    page.wait_for_timeout(400)
    shot(page, "05_sidepanel_comments")
    page.get_by_text("历史", exact=True).first.click()
    page.wait_for_timeout(400)
    shot(page, "06_sidepanel_history")
    # 关闭侧边面板，避免遮挡后续操作
    try:
        page.get_by_label("收起面板").click(timeout=2000)
        page.wait_for_timeout(300)
    except Exception:
        pass

    # 5) 右键节点 -> 上下文菜单
    # 先确保侧边面板已关闭（它可能遮挡画布）
    try:
        page.get_by_label("收起面板").click(timeout=2000)
        page.wait_for_timeout(300)
    except Exception:
        pass
    node = page.locator(".react-flow__node").last  # 用最上层节点避免被遮挡
    node.click(button="right")
    page.wait_for_timeout(500)
    menu_visible = page.locator("text=复制").count() > 0 and page.locator("text=删除").count() > 0
    print(f"[check] context menu (复制/删除) visible: {menu_visible}")
    shot(page, "07_context_menu")
    page.mouse.click(700, 450)  # 关闭菜单

    # 6) 快捷键 Delete 删除选中节点
    page.locator(".react-flow__node").last.click()
    page.wait_for_timeout(300)
    cnt_before_del = node_count(page)
    page.keyboard.press("Delete")
    page.wait_for_timeout(500)
    cnt_after_del = node_count(page)
    print(f"[check] Delete shortcut: {cnt_before_del} -> {cnt_after_del} (expect -1)")
    shot(page, "08_after_delete")

    # 7) 深色主题
    page.get_by_text("深", exact=True).first.click()
    page.wait_for_timeout(500)
    is_dark = "dark" in (page.evaluate("document.documentElement.className") or "")
    print(f"[check] dark theme applied: {is_dark}")
    shot(page, "09_dark_theme")

    # 汇总
    print("\n=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:30]:
            print(" ", e)
    else:
        print("  (none)")
    print(f"\nTOTAL console errors: {len(errors)}")
    browser.close()
