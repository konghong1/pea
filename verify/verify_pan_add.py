"""Verify: 画布左键平移 + 持续添加节点 + Shift 框选。
复用 _debug_drag.py 的注册/进画布流程。"""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("C:/workspace/pea/verify/shots")
OUT.mkdir(parents=True, exist_ok=True)
errors = []

def vp_transform(page):
    return page.evaluate("""() => {
        const vp = document.querySelector('.react-flow__viewport');
        return vp ? getComputedStyle(vp).transform : null;
    }""")

def node_count(page):
    return page.locator(".react-flow__node").count()

def find_empty(page):
    """找一个落在 react-flow 空白 pane 上的屏幕坐标（避开节点/浮层）。"""
    return page.evaluate("""() => {
        const cands = [];
        for (let y = 120; y < window.innerHeight - 120; y += 80)
            for (let x = 80; x < window.innerWidth - 80; x += 80)
                cands.push([x, y]);
        for (const [x, y] of cands) {
            const el = document.elementFromPoint(x, y);
            if (el && (el.classList.contains('react-flow__pane')
                || el.classList.contains('react-flow__renderer')
                || el.classList.contains('react-flow__viewport'))) {
                return { x, y };
            }
        }
        return null;
    }""")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and errors.append(m.text[:200]))
    page.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)[:200]))

    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(800)
    ts = int(time.time() * 1000)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', f"pan_{ts}@pea.ai")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "Pan")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)

    # 注册后进入工作空间，需「新建项目」才会真正进入画布
    if page.locator(".react-flow__viewport").count() == 0:
        page.get_by_role("button", name="新建项目").first.click()
        page.wait_for_timeout(3000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    page.wait_for_timeout(1500)

    print("== 初始节点数:", node_count(page))

    # ---- 1) 滚轮平移画布（Figma 风格）----
    t1 = vp_transform(page)
    page.mouse.wheel(-180, -120)
    page.wait_for_timeout(400)
    t2 = vp_transform(page)
    panned = t1 != t2
    print(f"[平移-滚轮] before={t1}")
    print(f"[平移-滚轮] after ={t2}")
    print(f"[平移-滚轮] 结果: {'PASS' if panned else 'FAIL'}")

    # ---- 2) 通过工具栏持续添加节点 ----
    def add_via_toolbar(kind):
        page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        label = {"text": "文本", "image": "图片", "video": "视频", "audio": "音频"}[kind]
        for it in page.locator(".pea-add-menu-item").all():
            if label in (it.text_content() or ""):
                box = it.bounding_box()
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.wait_for_timeout(600)
                page.mouse.move(10, 10)
                page.wait_for_timeout(300)
                return
        raise RuntimeError(f"menu item {kind} not found")

    c0 = node_count(page)
    add_via_toolbar("text"); c1 = node_count(page)
    add_via_toolbar("image"); c2 = node_count(page)
    print(f"[加节点-工具栏] {c0} -> {c1} -> {c2}  {'PASS' if c2 == c0 + 2 else 'FAIL'}")

    # ---- 3) 双击空白 -> 节点库 -> 加视频 ----
    empty = find_empty(page)
    assert empty, "找不到空白画布区域"
    page.mouse.dblclick(empty["x"], empty["y"])
    page.wait_for_selector(".pea-add-menu", timeout=4000)
    for it in page.locator(".pea-add-menu-item").all():
        if "视频" in (it.text_content() or ""):
            box = it.bounding_box()
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            break
    page.wait_for_timeout(600)
    page.mouse.move(10, 10)
    page.wait_for_timeout(300)
    c3 = node_count(page)
    print(f"[加节点-双击] {c2} -> {c3}  {'PASS' if c3 == c2 + 1 else 'FAIL'}")
    print(f"[总节点数] {c3}  (持续添加 OK)")

    # ---- 4) 直接拖拽框选（Figma 风格：拖拽=框选，滚轮平移）----
    # 不需要按 Shift，直接在空白处拖拽即可框选
    e2 = find_empty(page)
    sx, sy = (e2 or {"x": 200, "y": 200})["x"], (e2 or {"x": 200, "y": 200})["y"]
    t_before = vp_transform(page)  # 拖拽前的 viewport
    page.mouse.move(sx, sy)
    page.mouse.down()
    for i in range(1, 21):
        page.mouse.move(sx + i * 18, sy + i * 14)
        page.wait_for_timeout(15)
    sel_box = page.locator(".react-flow__selection").count()
    t_after = vp_transform(page)  # 拖拽后的 viewport
    page.mouse.up()
    page.wait_for_timeout(300)
    sel_ok = sel_box > 0
    no_pan = (t_before == t_after)  # 框选拖拽不应改变 viewport
    print(f"[框选] .react-flow__selection 出现: {sel_ok} (count={sel_box}), viewport未变: {no_pan}")
    print(f"[框选] before={t_before}, after={t_after}")
    print(f"[框选] 结果: {'PASS' if sel_ok and no_pan else 'FAIL'}")

    page.screenshot(path=str(OUT / "verify_pan_add.png"))
    browser.close()

print("\n== CONSOLE ERRORS ==", len(errors))
for e in errors[:20]:
    print("  ", e)
result = {
    "pan": panned, "add_toolbar": c2 == c0 + 2, "add_dblclick": c3 == c2 + 1,
    "shift_select": sel_ok and no_pan, "console_errors": len(errors)
}
print("RESULT:", json.dumps(result, ensure_ascii=False))
