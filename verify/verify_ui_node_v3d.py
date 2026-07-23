"""
画布节点视觉 v3 验证（对齐 pea-canvas-v12 截图1/3/4/5/6）。
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time
import sys

OUT = Path(__file__).parent / "shots"
OUT.mkdir(exist_ok=True)
URL = "http://localhost:8088"


def shot(page, name: str):
    p = OUT / f"uir3_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"  saved {p.name}")


def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(800)
        ts = int(time.time() * 1000)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', f"uir3d_{ts}@pea.ai")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "UIR3d")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(5000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        def ensure_menu_open():
            """用真实鼠标点击工具栏触发菜单"""
            if page.locator(".pea-add-menu").count() > 0:
                return
            btn = page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first
            btn.click()
            page.wait_for_selector(".pea-add-menu", timeout=4000)
            page.wait_for_timeout(200)

        def pick_menu(text):
            ensure_menu_open()
            items = page.locator(".pea-add-menu-item").all()
            for it in items:
                if text in (it.text_content() or ""):
                    box = it.bounding_box()
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    page.wait_for_timeout(800)
                    menu_count = page.locator(".pea-add-menu").count()
                    nodes_count = page.locator(".react-flow__node").count()
                    print(f"  [debug] after click '{text}': menu={menu_count}, nodes={nodes_count}")
                    return True
            raise RuntimeError(f"menu item {text!r} not found")

        def select_node(kind: str):
            # 直接点 body-card 中心，避开容器 hit-test 校验
            n = page.locator(f'.pea-node[data-kind="{kind}"] .pea-node-body-card')
            n.first.click(force=True)
            page.wait_for_timeout(400)

        # 1) 默认画布
        shot(page, "01_default_canvas")

        # 2) 通过工具栏触发 AddNodeMenu（截图1）
        ensure_menu_open()
        shot(page, "02_add_menu")

        # 3) 悬停"图片"行（截图1 高亮态）
        items = page.locator(".pea-add-menu-item").all()
        for it in items:
            if "图片" in (it.text_content() or ""):
                it.hover()
                break
        page.wait_for_timeout(200)
        shot(page, "03_menu_hover_image")

        # 4) 选"文本" → 节点 + 输入栏
        pick_menu("文本")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        select_node("text")
        shot(page, "04_text_with_inputbar")
        ta = page.locator(".node-input-textarea").first
        if ta.count() > 0:
            ta.fill("一段关于太空歌剧的描述")
            page.wait_for_timeout(300)
            shot(page, "05_text_typed")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 5) 选"图片"
        pick_menu("图片")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        select_node("image")
        shot(page, "06_image_with_inputbar")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 6) 选"视频"
        pick_menu("视频")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        select_node("video")
        shot(page, "07_video_with_inputbar")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 7) 选"音频"
        pick_menu("音频")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        select_node("audio")
        shot(page, "08_audio_with_inputbar")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 8) 全景
        page.mouse.move(20, 20)
        page.wait_for_timeout(400)
        shot(page, "09_all_four_nodes")

        # 9) 文本节点 + 浮动工具条
        select_node("text")
        page.locator('.pea-node[data-kind="text"] .pea-node-text-edit').first.click(force=True)
        page.wait_for_timeout(400)
        shot(page, "10_text_with_text_toolbar")

        # 10) 再触发一次菜单，截图（验证 3D世界 Beta 标签可见）
        ensure_menu_open()
        shot(page, "11_add_menu_with_beta_tags")

        browser.close()

    print(f"\nTOTAL console errors/warnings: {len(errors)}")
    for e in errors[:20]:
        print("  ", e)

    real_errors = [e for e in errors if "error:" in e or "pageerror" in e]
    return 0 if not real_errors else 1


if __name__ == "__main__":
    sys.exit(main())