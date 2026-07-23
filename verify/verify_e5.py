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


def in_toolbar(page, label):
    return page.locator(".pea-toolbar").get_by_role("button", name=label, exact=True).first


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 登录（用唯一邮箱避免画布状态污染；先切到注册模式）
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "E5Bot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    shot(page, "01_workspace")

    # 2) 添加生成节点（左侧工具栏「添加节点」打开库 → 选「生成」）
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    before = node_count(page)
    in_toolbar(page, "添加节点（双击画布也可打开）").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="生成", exact=True).first.click()
    page.wait_for_timeout(800)
    after_add = node_count(page)
    print(f"[check] add generate node: {before} -> {after_add} (expect +1)")
    shot(page, "02_add_node")

    # 3) 副驾驶：通常默认展开，若收起则点机器人图标打开 → 点"⚡ 生成图片"技能
    if page.get_by_role("button", name="打开副驾驶").count() > 0:
        page.get_by_role("button", name="打开副驾驶").first.click()
        page.wait_for_timeout(800)
    # force=True 跳过 z-index 严格的 hit-test 校验（实际坐标已不重叠）
    page.get_by_text("⚡ 生成图片", exact=False).first.click(force=True)
    page.wait_for_timeout(1500)
    after_agent = node_count(page)
    print(f"[check] agent add node: {after_add} -> {after_agent} (expect +1)")
    agent_has_reply = page.locator("text=已为你添加一个").count() > 0 or page.locator("text=已记录你的意图").count() > 0
    print(f"[check] agent reply shown: {agent_has_reply}")
    shot(page, "03_agent_panel")

    # 4) 侧边面板：搜索/评论/历史/文件
    in_toolbar(page, "搜索").click()
    page.wait_for_timeout(600)
    shot(page, "04_sidepanel_search")
    in_toolbar(page, "评论").click()
    page.wait_for_timeout(400)
    shot(page, "05_sidepanel_comments")
    in_toolbar(page, "历史记录").click()
    page.wait_for_timeout(400)
    shot(page, "06_sidepanel_history")
    # 关闭侧边面板
    try:
        page.get_by_label("收起面板").click(timeout=2000)
        page.wait_for_timeout(300)
    except Exception:
        pass

    # 5) 右键节点 -> 上下文菜单
    try:
        page.get_by_label("收起面板").click(timeout=2000)
        page.wait_for_timeout(300)
    except Exception:
        pass
    node = page.locator(".react-flow__node").last
    node.click(button="right", force=True)
    page.wait_for_timeout(500)
    menu_visible = page.locator("text=复制").count() > 0 and page.locator("text=删除").count() > 0
    print(f"[check] context menu (复制/删除) visible: {menu_visible}")
    shot(page, "07_context_menu")
    page.mouse.click(700, 450)  # 关闭菜单

    # 6) Delete 快捷键
    page.locator(".react-flow__node").last.click(force=True)
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

    print("\n=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:30]:
            print(" ", e)
    else:
        print("  (none)")
    print(f"\nTOTAL console errors: {len(errors)}")
    browser.close()
