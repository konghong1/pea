"""E10 · 节点库（添加节点菜单）回归（对齐当前 UI，2026-07-24 重写）

覆盖：
- 注册唯一账号并进入工作空间
- 左侧工具栏「添加节点」打开节点库（.pea-add-menu + 遮罩 fixed inset-0 z-40）
- 选「图片」节点 → 画布 +1，且菜单自动关闭
- 双击画布空白 → 节点库再次打开
- 选「文本」节点 → 画布再 +1
- 0 console error（硬标准）

修正要点：
- 原脚本用固定账号 verify@pea.ai 登录（很可能不存在 → 卡在登录页），改为注册唯一账号。
- 原脚本用 div.fixed.inset-0.z-50 判定弹窗，实际遮罩为 z-40；改用 .pea-add-menu。
- 原脚本选「生成」项，节点库无此项（仅 文本/图片/视频/音频/3D世界/播放列表/上传），改为「图片」。
"""
import os
import sys
import uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"e10_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []
checks = []


def node_count(page):
    return page.locator(".react-flow__node").count()


def in_toolbar(page, label):
    return page.locator(".pea-toolbar").get_by_role("button", name=label, exact=True).first


def ensure_canvas(page):
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
    b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    pg.goto(BASE, wait_until="networkidle")
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="没有账号？去注册").first.click()
    pg.wait_for_timeout(300)
    pg.fill('input[placeholder="you@pea.ai"]', EMAIL)
    pg.fill('input[placeholder="至少 8 位"]', PW)
    pg.fill('input[placeholder="可选"]', "E10Bot")
    pg.locator("form button[type=submit]").click()
    pg.wait_for_timeout(4000)
    ensure_canvas(pg)

    # 1) 打开节点库（左侧工具栏「添加节点」）
    in_toolbar(pg, "添加节点（双击画布也可打开）").click()
    pg.wait_for_timeout(500)
    lib_shown = pg.locator(".pea-add-menu").count() > 0
    checks.append(("节点库(.pea-add-menu) 打开", lib_shown))

    before = node_count(pg)
    # 2) 选「图片」
    pg.locator(".pea-add-menu").get_by_text("图片", exact=True).first.click()
    pg.wait_for_timeout(700)
    after_add = node_count(pg)
    checks.append((f"从库添加图片节点: {before}->{after_add} (+1)", after_add == before + 1))
    # 菜单应自动关闭（onPick 内调用 onClose）
    try:
        pg.wait_for_selector(".pea-add-menu", state="detached", timeout=4000)
        auto_closed = True
    except Exception:
        auto_closed = pg.locator(".pea-add-menu").count() == 0
    checks.append(("选完节点后菜单自动关闭", auto_closed))

    # 3) 双击画布空白打开库（用坐标式双击避免落在节点上）
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    pg.mouse.dblclick(1000, 520)
    pg.wait_for_timeout(500)
    dbl_open = pg.locator(".pea-add-menu").count() > 0
    checks.append(("双击画布打开节点库", dbl_open))

    # 4) 选「文本」
    if dbl_open:
        pg.locator(".pea-add-menu").get_by_text("文本", exact=True).first.click()
        pg.wait_for_timeout(700)
    after2 = node_count(pg)
    checks.append((f"从库添加文本节点: {after_add}->{after2} (+1)", after2 == after_add + 1))

    pg.wait_for_timeout(300)
    pg.screenshot(path=os.path.join(SHOTS, "e10_node_library.png"))

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

    b.close()
    ok = all(ok for _, ok in checks) and len(errors) == 0
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)
