import os, time, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
errors = []

def node_count(page):
    return page.locator(".react-flow__node").count()

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    pg.goto(BASE, wait_until="networkidle")
    pg.wait_for_timeout(800)
    pg.fill('input[placeholder="you@pea.ai"]', 'verify@pea.ai')
    pg.fill('input[placeholder="至少 8 位"]', 'password123')
    pg.locator("form button[type=submit]").click()
    pg.wait_for_timeout(2500)
    pg.wait_for_selector(".react-flow__viewport", timeout=15000)

    # 1) 打开节点库（顶栏按钮）
    pg.get_by_role("button", name="节点库").click()
    pg.wait_for_timeout(500)
    lib = pg.locator("div.fixed.inset-0.z-50")
    lib_shown = lib.count() > 0
    print(f"[check] node-library modal shown: {lib_shown}")

    before = node_count(pg)
    # 2) 点击节点库内「生成」按钮（用 aria-label 精准匹配，避开顶栏「⚡ 生成」）
    lib.get_by_role("button", name="生成", exact=True).click()
    pg.wait_for_timeout(700)
    after_add = node_count(pg)
    print(f"[check] add 'generate' from library: {before} -> {after_add} (expect +1)")
    pg.keyboard.press("Escape")
    try:
        pg.wait_for_selector("div.fixed.inset-0.z-50", state="detached", timeout=4000)
        auto_closed = True
    except Exception as ex:
        auto_closed = False
        print("[WARN] library did not auto-close:", ex)
    print(f"[check] library auto-closed after pick: {auto_closed}")

    # 3) 双击画布打开库
    pg.locator(".react-flow__pane").first.dblclick()
    pg.wait_for_timeout(500)
    lib2 = pg.locator("div.fixed.inset-0.z-50")
    dbl_open = lib2.count() > 0
    print(f"[check] double-click opens library: {dbl_open}")

    # 4) 点击节点库内「文本」按钮
    if dbl_open:
        lib2.get_by_role("button", name="文本", exact=True).click()
        pg.wait_for_timeout(600)
        pg.keyboard.press("Escape")
    after2 = node_count(pg)
    print(f"[check] add 'text' via dblclick library: {after_add} -> {after2} (expect +1)")

    pg.wait_for_timeout(300)
    pg.screenshot(path=os.path.join(SHOTS, "e10_node_library.png"))

    b.close()

print("CONSOLE_ERRORS:", len(errors))
if errors:
    print("\n".join(errors[:10]))
ok = lib_shown and (not errors) and after_add == before + 1 and after2 == after_add + 1 and dbl_open
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
