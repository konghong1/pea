"""E5 · 画布基础交互回归（对齐当前 UI，2026-07-24 重写）

覆盖：
- 注册唯一账号并进入工作空间画布
- 左侧工具栏「添加节点」→ 选「图片」节点 (+1)
- 副驾驶：打开气泡 → ⚡生成图片 技能（节点 +1 且回复可见）
- 侧边栏「搜索」打开 SidePanel（含「收起面板」按钮）
- 右键节点弹出自定义菜单（复制 / ➕添加并连接 / 🗑删除）
- Delete 快捷键删除选中节点 (-1)
- 深 / 浅 主题切换
- 0 console error（硬标准）

选择器均对齐画布重设计后的真实 DOM。
"""
import os
import sys
import uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"e5_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []
checks = []


def shot(page, name):
    p = os.path.join(SHOTS, f"e5_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")


def node_count(page):
    return page.locator(".react-flow__node").count()


def in_toolbar(page, label):
    return page.locator(".pea-toolbar").get_by_role("button", name=label, exact=True).first


def ensure_canvas(page):
    """注册后确保进入画布视图（工作空间）。"""
    try:
        page.wait_for_selector(".react-flow__viewport", timeout=8000)
        return
    except Exception:
        pass
    btn = page.get_by_role("button", name="工作空间", exact=True)
    if btn.count() > 0:
        btn.first.click()
        page.wait_for_timeout(1200)
    page.wait_for_selector(".react-flow__viewport", timeout=20000)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册并进入工作空间
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "E5Bot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(4000)
    ensure_canvas(page)
    shot(page, "01_workspace")
    checks.append(("进入工作空间画布", True))

    # 2) 添加图片节点
    before = node_count(page)
    in_toolbar(page, "添加节点（双击画布也可打开）").click()
    page.wait_for_timeout(500)
    page.locator(".pea-add-menu").get_by_text("图片", exact=True).first.click()
    page.wait_for_timeout(800)
    after_add = node_count(page)
    checks.append((f"添加图片节点: {before}->{after_add} (+1)", after_add == before + 1))
    shot(page, "02_add_node")

    # 3) 副驾驶：打开气泡 → 发一条消息让技能芯片出现 → 点 ⚡生成图片
    bubble = page.get_by_role("button", name="打开副驾驶")
    if bubble.count() > 0:
        bubble.first.click()
        page.wait_for_timeout(800)
    # SKILLS 芯片仅在已有消息后渲染，先发一条不触发加节点的消息
    agent_input = page.locator(".pea-agent-panel").get_by_placeholder("描述创意", exact=False).first
    if agent_input.count() > 0:
        agent_input.fill("你好")
        page.wait_for_timeout(200)
        agent_input.press("Enter")
        page.wait_for_timeout(800)
    page.get_by_text("⚡ 生成图片", exact=False).first.click()
    page.wait_for_timeout(1500)
    after_agent = node_count(page)
    checks.append((f"副驾驶⚡生成图片: 节点 {after_add}->{after_agent} (+1)", after_agent == after_add + 1))
    agent_reply = page.locator("text=已为你添加一个").count() > 0
    checks.append(("副驾驶回复可见", agent_reply))
    shot(page, "03_agent_panel")
    # 收起副驾驶
    close = page.get_by_role("button", name="收起副驾驶")
    if close.count() > 0:
        close.first.click()
        page.wait_for_timeout(400)

    # 4) 侧边栏「搜索」打开 SidePanel
    in_toolbar(page, "搜索").click()
    page.wait_for_timeout(600)
    panel_open = page.get_by_role("button", name="收起面板", exact=True).count() > 0
    checks.append(("搜索打开侧边面板(含收起面板)", panel_open))
    shot(page, "04_sidepanel_search")
    if panel_open:
        page.get_by_role("button", name="收起面板", exact=True).first.click()
        page.wait_for_timeout(400)

    # 5) 右键节点 → 自定义菜单（坐标式，确保触发 onNodeContextMenu）
    page.mouse.click(720, 450)  # 清场
    page.wait_for_timeout(300)
    node = page.locator(".react-flow__node").last
    nb = node.bounding_box()
    page.mouse.click(nb["x"] + nb["width"] / 2, nb["y"] + nb["height"] / 2, button="right")
    page.wait_for_timeout(500)
    menu_ok = (
        page.get_by_text("复制节点", exact=False).count() > 0
        and page.get_by_text("添加并连接", exact=False).count() > 0
        and page.get_by_text("删除节点", exact=False).count() > 0
    )
    checks.append(("右键节点弹出自定义菜单(复制/添加并连接/删除)", menu_ok))
    shot(page, "05_context_menu")
    page.mouse.click(720, 450)  # 关菜单
    page.wait_for_timeout(300)

    # 6) Delete 快捷键删除选中节点
    node.click(force=True)
    page.wait_for_timeout(300)
    cnt_before_del = node_count(page)
    page.keyboard.press("Delete")
    page.wait_for_timeout(500)
    cnt_after_del = node_count(page)
    checks.append((f"Delete 快捷键: {cnt_before_del}->{cnt_after_del} (-1)", cnt_after_del == cnt_before_del - 1))
    shot(page, "06_after_delete")

    # 7) 主题切换（深 / 浅）
    page.locator(".pea-topnav .ant-segmented-item-label", has_text="深").first.click()
    page.wait_for_timeout(500)
    is_dark = "dark" in (page.evaluate("document.documentElement.className") or "")
    checks.append(("切换深色主题生效", is_dark))
    shot(page, "07_dark_theme")
    page.locator(".pea-topnav .ant-segmented-item-label", has_text="浅").first.click()
    page.wait_for_timeout(500)
    is_light = "dark" not in (page.evaluate("document.documentElement.className") or "")
    checks.append(("切换浅色主题生效", is_light))
    shot(page, "08_light_theme")

    # 结果
    print("\n=== CHECKS ===")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("\n=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:30]:
            print("  ", e)
    else:
        print("  (none)")
    print(f"\nTOTAL console errors: {len(errors)}")

    browser.close()
    ok = all(ok for _, ok in checks) and len(errors) == 0
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)
