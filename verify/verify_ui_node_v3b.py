"""
画布节点视觉 v3 验证（对齐 pea-canvas-v12 截图1/3/4/5/6）：
- 双击画布弹出 AddNodeMenu
- 4 种节点类型视觉：text/image/video/audio
- 节点下方输入栏按类型显示对应模型工具栏
- 0 console error
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
        page.fill('input[placeholder="you@pea.ai"]', f"uir3b_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "UIR3b")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(5000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        # 获取画布 pane 尺寸用于空白双击点
        pane = page.locator(".react-flow__pane").first
        pb = pane.bounding_box()

        def dblclick_blank(x, y):
            """在 pane 空白处双击（远离节点）"""
            # 先移到画布左上角清掉 hover
            page.mouse.move(20, 20)
            page.wait_for_timeout(50)
            # 工具栏和 controls 占用的左侧 60px / 右下角避免
            page.mouse.dblclick(x, y)
            page.wait_for_timeout(300)

        # 1) 默认画布
        shot(page, "01_default_canvas")

        # 2) 双击中央空白，弹出 AddNodeMenu
        dblclick_blank(pb["x"] + pb["width"] / 2, pb["y"] + pb["height"] / 2)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.wait_for_timeout(300)
        shot(page, "02_dblclick_add_menu")

        # 3) 悬停"图片"行（截图1 高亮态）
        page.get_by_role("menuitem").filter(has_text="图片").hover()
        page.wait_for_timeout(200)
        shot(page, "03_menu_hover_image")

        # 4) 选"文本"
        page.get_by_role("menuitem").filter(has_text="文本").click()
        page.wait_for_timeout(500)
        # 让选区消掉以查看节点本身
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        # 再点击节点触发输入栏
        text_nodes = page.locator('.react-flow__node[data-kind="text"]')
        if text_nodes.count() > 0:
            text_nodes.first.click()
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
        dblclick_blank(pb["x"] + 220, pb["y"] + pb["height"] / 2)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.get_by_role("menuitem").filter(has_text="图片").click()
        page.wait_for_timeout(500)
        img_nodes = page.locator('.react-flow__node[data-kind="image"]')
        if img_nodes.count() > 0:
            img_nodes.first.click()
            page.wait_for_timeout(400)
            shot(page, "06_image_with_inputbar")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # 6) 选"视频"
        dblclick_blank(pb["x"] + 480, pb["y"] + pb["height"] / 2)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.get_by_role("menuitem").filter(has_text="视频").click()
        page.wait_for_timeout(500)
        vid_nodes = page.locator('.react-flow__node[data-kind="video"]')
        if vid_nodes.count() > 0:
            vid_nodes.first.click()
            page.wait_for_timeout(400)
            shot(page, "07_video_with_inputbar")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # 7) 选"音频"
        dblclick_blank(pb["x"] + 740, pb["y"] + pb["height"] / 2)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.get_by_role("menuitem").filter(has_text="音频").click()
        page.wait_for_timeout(500)
        aud_nodes = page.locator('.react-flow__node[data-kind="audio"]')
        if aud_nodes.count() > 0:
            aud_nodes.first.click()
            page.wait_for_timeout(400)
            shot(page, "08_audio_with_inputbar")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

        # 8) 全景：把鼠标移到角落，所有节点都不被 hover/选中
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