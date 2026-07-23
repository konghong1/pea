"""
画布节点视觉 v3 验证（对齐 pea-canvas-v12 截图1/3/4/5/6）。
通过左侧工具栏"+ 添加节点"按钮触发菜单（避开双击命中节点的问题）。
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
        page.fill('input[placeholder="you@pea.ai"]', f"uir3c_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "UIR3c")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(5000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        # 通过工具栏触发 AddNodeMenu（不依赖双击命中）
        def ensure_menu_open():
            if page.locator(".pea-add-menu").count() > 0:
                return
            # 用 JS 强制点击，绕过 z-40 遮罩层
            page.evaluate(
                """() => {
                    const btn = document.querySelector('.pea-tlb-btn[aria-label*="添加节点"]');
                    if (btn) btn.click();
                }"""
            )
            page.wait_for_selector(".pea-add-menu", timeout=4000)
            page.wait_for_timeout(200)

        def pick_menu(text):
            ensure_menu_open()
            # 用 JS 在菜单项 DOM 上直接派发事件，绕过 z-40 遮罩
            page.evaluate(
                """(label) => {
                    const items = document.querySelectorAll('.pea-add-menu .pea-add-menu-item');
                    for (const it of items) {
                        if (it.textContent.includes(label)) {
                            it.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                text,
            )
            page.wait_for_timeout(600)

        # 1) 默认画布
        shot(page, "01_default_canvas")

        # 2) 通过工具栏触发 AddNodeMenu，截图（截图1）
        ensure_menu_open()
        shot(page, "02_add_menu")

        # 3) 悬停"图片"行（截图1 高亮态）
        page.locator(".pea-add-menu-item").filter(has_text="图片").hover(force=True)
        page.wait_for_timeout(200)
        shot(page, "03_menu_hover_image")

        # 4) 选"文本"
        print("[debug] step 4 - pick text")
        pick_menu("文本")
        page.wait_for_timeout(300)
        print(f"[debug] text nodes count: {page.locator('.react-flow__node[data-kind=\"text\"]').count()}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        tn = page.locator('.react-flow__node[data-kind="text"]')
        if tn.count() > 0:
            tn.first.click()
            page.wait_for_timeout(400)
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
        img = page.locator('.react-flow__node[data-kind="image"]')
        if img.count() > 0:
            img.first.click()
            page.wait_for_timeout(400)
            shot(page, "06_image_with_inputbar")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # 6) 选"视频"
        pick_menu("视频")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        vid = page.locator('.react-flow__node[data-kind="video"]')
        if vid.count() > 0:
            vid.first.click()
            page.wait_for_timeout(400)
            shot(page, "07_video_with_inputbar")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # 7) 选"音频"
        pick_menu("音频")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        aud = page.locator('.react-flow__node[data-kind="audio"]')
        if aud.count() > 0:
            aud.first.click()
            page.wait_for_timeout(400)
            shot(page, "08_audio_with_inputbar")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # 8) 全景：所有节点不 hover/选中
        page.mouse.move(20, 20)
        page.wait_for_timeout(400)
        shot(page, "09_all_four_nodes")

        # 9) 点击文本节点触发浮动工具条
        if page.locator('.react-flow__node[data-kind="text"]').count() > 0:
            tn = page.locator('.react-flow__node[data-kind="text"]').first
            tn.click()
            page.wait_for_timeout(400)
            tn.locator(".pea-node-text-edit").click()
            page.wait_for_timeout(400)
            shot(page, "10_text_with_text_toolbar")

        browser.close()

    print(f"\nTOTAL console errors/warnings: {len(errors)}")
    for e in errors[:20]:
        print("  ", e)

    return 0 if not any("error:" in e or "pageerror" in e for e in errors) else 1


if __name__ == "__main__":
    sys.exit(main())