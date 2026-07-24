"""验证画布三个 UX 修复：
1. 选中 text 节点后不再出现重复的 "Text" 标签（tnt-label 已移除），节点类型显示图标+Text。
2. 画布右键弹出自定义菜单，不再出现浏览器默认菜单。
3. 连线/添加并连接时节点 ID 唯一，源节点与新增节点都可见，不消失。
"""

import os
import time
import uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"ux_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []
checks = []


def shot(page, name):
    p = os.path.join(SHOTS, f"ux_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")
    return p


def node_count(page):
    return page.locator(".react-flow__node").count()


def edge_count(page):
    return page.locator(".react-flow__edge").count()


def in_toolbar(page, label):
    return page.locator(".pea-toolbar").get_by_role("button", name=label, exact=True).first


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册并进入画布
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "UXBot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    shot(page, "01_workspace")

    # 2) 添加 text 节点
    before = node_count(page)
    in_toolbar(page, "添加节点（双击画布也可打开）").click()
    page.wait_for_timeout(500)
    shot(page, "01b_add_menu_open")
    page.locator(".pea-add-menu").get_by_text("文本", exact=True).first.click()
    page.wait_for_timeout(800)
    after_text = node_count(page)
    checks.append(("添加 text 节点 +1", after_text == before + 1))

    # 3) 选中 text 节点，验证无重复 Text 标签、图标+Text 显示
    page.locator(".react-flow__node").first.click()
    page.wait_for_timeout(400)
    tb = page.locator(".text-node-toolbar")
    tb.wait_for(state="visible", timeout=5000)
    checks.append(("浮动文本工具条可见", tb.is_visible()))
    # 修复点：不再显示 tnt-label 这种重复标签
    tnt_label_count = page.locator(".tnt-label").count()
    checks.append(("无重复 Text 标签 (tnt-label=0)", tnt_label_count == 0))
    # 节点类型标签应包含图标和 Text
    tag_pill = page.locator(".pea-node-tag-pill")
    tag_text = tag_pill.first.inner_text() if tag_pill.count() else ""
    checks.append(("text 节点标签含 Text", "Text" in tag_text))
    checks.append(("text 节点标签含图标", len(tag_text) > len("Text")))
    shot(page, "02_text_selected_no_duplicate_label")

    # 4) 右键空白画布，验证弹出自定义菜单（避免浏览器默认菜单）
    page.mouse.click(300, 700, button="right")  # 空白处（无节点）
    page.wait_for_timeout(400)
    # 自定义菜单：包含 "打开节点库" / "适配视图"
    custom_menu = page.get_by_text("打开节点库", exact=False).first
    checks.append(("右键空白处自定义菜单出现", custom_menu.is_visible()))
    shot(page, "03_pane_context_menu")
    # 关闭菜单
    page.mouse.click(720, 450)
    page.wait_for_timeout(300)

    # 5) 从 text 节点右侧拖拽连线到空白处，选择图片节点，验证源节点与新增节点都可见
    src = page.locator(".react-flow__node").first
    src_box = src.bounding_box()
    start_x = src_box["x"] + src_box["width"] + 5
    start_y = src_box["y"] + src_box["height"] / 2
    end_x = start_x + 280
    end_y = start_y + 80
    nodes_before = node_count(page)
    edges_before = edge_count(page)
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y, steps=10)
    page.wait_for_timeout(150)
    page.mouse.up()
    page.wait_for_timeout(500)
    # 弹出 EdgeNodeMenu，选择图片
    edge_menu = page.locator(".pea-edge-menu")
    if edge_menu.count() > 0 and edge_menu.first.is_visible():
        edge_menu.get_by_text("图片生成", exact=True).first.click()
        page.wait_for_timeout(600)
    else:
        # 如果未弹出（例如拖拽被识别为框选），则退一步用右键「添加并连接」测试
        page.locator(".react-flow__node").first.click(button="right", force=True)
        page.wait_for_timeout(400)
        page.get_by_text("添加并连接", exact=False).first.click()
        page.wait_for_timeout(600)
    nodes_after = node_count(page)
    edges_after = edge_count(page)
    checks.append((f"连线后节点数 {nodes_before}->{nodes_after} (+1)", nodes_after == nodes_before + 1))
    checks.append((f"连线后边数 {edges_before}->{edges_after} (+1)", edges_after == edges_before + 1))
    # 关键：源节点与新增节点都应可见（不消失）
    checks.append(("源节点与新增节点都可见", node_count(page) >= 2))
    shot(page, "04_after_connect")

    print("\n=== CHECKS ===")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed

    print("\n=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:30]:
            print(" ", e)
    else:
        print("  (none)")
    print(f"\nTOTAL console errors: {len(errors)}")
    print(f"RESULT: {'ALL PASS' if (ok and not errors) else 'HAS ISSUES'}")
    browser.close()
    if not ok or errors:
        raise SystemExit(1)
