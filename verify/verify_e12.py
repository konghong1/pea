import os, time, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"e12_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []
checks = []


def shot(page, name):
    p = os.path.join(SHOTS, f"e12_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")
    return p


def node_count(page):
    return page.locator(".react-flow__node").count()


def edge_count(page):
    return page.locator(".react-flow__edge").count()


def sel_count(page):
    return page.locator(".react-flow__node.selected").count()


def in_toolbar(page, label):
    return page.locator(".pea-toolbar").get_by_role("button", name=label, exact=True).first


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册（唯一邮箱避免画布状态污染）
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "E12Bot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    shot(page, "01_workspace")

    # 2) 添加 text 节点（库 → 文本）
    before = node_count(page)
    in_toolbar(page, "添加节点（双击画布也可打开）").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="文本", exact=True).first.click()
    page.wait_for_timeout(800)
    after_text = node_count(page)
    checks.append(("添加 text 节点 +1", after_text == before + 1))

    # 3) 浮动文本工具条出现（选中 text 节点后浮现）
    page.locator(".react-flow__node").first.click()
    page.wait_for_timeout(300)
    tb = page.locator(".text-node-toolbar")
    tb.wait_for(state="visible", timeout=5000)
    tb_visible = tb.is_visible()
    label_ok = page.locator(".tnt-label", has_text="Text").count() > 0
    checks.append(("浮动文本工具条可见", tb_visible))
    checks.append(("工具条含 Text 标签", label_ok))
    shot(page, "02_floating_toolbar")

    # 4) H2 / B 格式化作用于画布 text 节点
    editable = page.locator(".pea-node.selected .pea-node-text-edit").first
    editable.wait_for(state="visible", timeout=5000)

    def select_all(ed):
        ed.evaluate(
            "el=>{const r=document.createRange();r.selectNodeContents(el);"
            "const s=window.getSelection();s.removeAllRanges();s.addRange(r);}"
        )

    select_all(editable)
    page.wait_for_timeout(150)
    page.locator(".text-node-toolbar").get_by_role("button", name="Heading 2", exact=True).click()
    page.wait_for_timeout(200)
    h2_html = editable.inner_html().lower()
    h2_active = page.locator(".tnt-btn.active", has_text="H2").count() > 0
    checks.append(("H2 按钮 active", h2_active))
    checks.append(("正文含 <h2>", "h2" in h2_html))
    select_all(editable)
    page.wait_for_timeout(100)
    page.locator(".text-node-toolbar").get_by_role("button", name="加粗", exact=True).click()
    page.wait_for_timeout(200)
    bold_html = editable.inner_html().lower()
    checks.append(("正文含加粗标签", ("<b" in bold_html) or ("<strong" in bold_html) or ("font-weight" in bold_html)))
    shot(page, "03_format_h2_bold")

    # 5) Shift 框选多选
    # 先再加一个节点，确保 >=2
    in_toolbar(page, "添加节点（双击画布也可打开）").click()
    page.wait_for_timeout(400)
    page.get_by_role("button", name="生成", exact=True).first.click()
    page.wait_for_timeout(600)
    cnt_before_box = node_count(page)
    # 关闭可能打开的库弹层/菜单
    page.mouse.click(720, 450)
    page.wait_for_timeout(300)
    # shift 拖拽出框选（自管选区）
    page.keyboard.down("Shift")
    page.mouse.move(150, 150)
    page.mouse.down()
    page.mouse.move(600, 500, steps=10)
    page.wait_for_timeout(150)
    box_visible = page.locator(".pea-sel-box").count() > 0
    page.mouse.move(1300, 850, steps=10)
    page.mouse.up()
    page.keyboard.up("Shift")
    page.wait_for_timeout(500)
    checks.append(("框选矩形出现", box_visible))
    sel = page.locator(".pea-node.selected").count()
    checks.append((f"Shift 框选选中节点 >=2 (命中 {sel}/{cnt_before_box})", sel >= 2))
    shot(page, "04_shift_box_select")

    # 6) 右键「添加并连接」
    page.mouse.click(720, 450)  # 关闭框选/菜单
    page.wait_for_timeout(300)
    node = page.locator(".react-flow__node").first
    nodes_before = node_count(page)
    edges_before = edge_count(page)
    node.click(button="right", force=True)
    page.wait_for_timeout(400)
    page.get_by_text("添加并连接", exact=False).first.click()
    page.wait_for_timeout(600)
    nodes_after = node_count(page)
    edges_after = edge_count(page)
    checks.append((f"添加并连接: 节点 {nodes_before}->{nodes_after} (+1)", nodes_after == nodes_before + 1))
    checks.append((f"添加并连接: 边 {edges_before}->{edges_after} (+1)", edges_after == edges_before + 1))
    shot(page, "05_add_connected")

    # 7) 深色主题
    page.get_by_text("深", exact=True).first.click()
    page.wait_for_timeout(400)
    is_dark = "dark" in (page.evaluate("document.documentElement.className") or "")
    checks.append(("深色主题应用", is_dark))
    shot(page, "06_dark")

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
