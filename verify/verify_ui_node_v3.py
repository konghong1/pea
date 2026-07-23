"""
画布节点视觉 v3 验证（对齐 pea-canvas-v12 截图1/3/4/5/6）：
- 双击画布弹出 AddNodeMenu（截图1）
- 4 种节点类型视觉：text/image/video/audio（截图3/4/5/6）
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
        # 注册
        ts = int(time.time() * 1000)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', f"uir3_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "UIR3")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(5000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        # 1) 默认画布
        shot(page, "01_default_canvas")

        # 2) 双击画布空白处，弹出 AddNodeMenu
        pane = page.locator(".react-flow__pane").first
        box = pane.bounding_box()
        page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.wait_for_timeout(300)
        shot(page, "02_dblclick_add_menu")

        # 3) 悬停"图片"行
        page.get_by_role("menuitem").filter(has_text="图片").hover()
        page.wait_for_timeout(200)
        shot(page, "03_menu_hover_image")

        # 4) 点击"文本"加 text 节点
        page.get_by_role("menuitem").filter(has_text="文本").click()
        page.wait_for_timeout(500)
        shot(page, "04_text_node")
        # 让选区消掉，捕获未选中态
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        shot(page, "05_text_node_deselected")

        # 5) 双击 → 选"图片"
        page.mouse.dblclick(box["x"] + box["width"] / 2 - 300, box["y"] + box["height"] / 2)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.get_by_role("menuitem").filter(has_text="图片").click()
        page.wait_for_timeout(500)
        shot(page, "06_image_node")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 6) 双击 → 选"视频"
        page.mouse.dblclick(box["x"] + box["width"] / 2 + 300, box["y"] + box["height"] / 2)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.get_by_role("menuitem").filter(has_text="视频").click()
        page.wait_for_timeout(500)
        shot(page, "07_video_node")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 7) 双击 → 选"音频"
        page.mouse.dblclick(box["x"] + box["width"] / 2 - 300, box["y"] + box["height"] / 2 + 200)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.get_by_role("menuitem").filter(has_text="音频").click()
        page.wait_for_timeout(500)
        shot(page, "08_audio_node")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 8) 点击 text 节点触发输入栏
        # 找到第一个 text 节点并点击
        text_nodes = page.locator('.react-flow__node[data-kind="text"]')
        if text_nodes.count() > 0:
            text_nodes.first.click()
            page.wait_for_timeout(400)
            shot(page, "09_text_with_inputbar")
            # 在输入栏输入文本
            ta = page.locator(".node-input-textarea").first
            if ta.count() > 0:
                ta.fill("一段关于太空歌剧的描述")
                page.wait_for_timeout(300)
                shot(page, "10_text_typed")

        # 9) 点击 image 节点查看其输入栏
        img_nodes = page.locator('.react-flow__node[data-kind="image"]')
        if img_nodes.count() > 0:
            img_nodes.first.click()
            page.wait_for_timeout(400)
            shot(page, "11_image_with_inputbar")

        # 10) 点击 video 节点查看其输入栏
        vid_nodes = page.locator('.react-flow__node[data-kind="video"]')
        if vid_nodes.count() > 0:
            vid_nodes.first.click()
            page.wait_for_timeout(400)
            shot(page, "12_video_with_inputbar")

        # 11) 点击 audio 节点查看其输入栏
        aud_nodes = page.locator('.react-flow__node[data-kind="audio"]')
        if aud_nodes.count() > 0:
            aud_nodes.first.click()
            page.wait_for_timeout(400)
            shot(page, "13_audio_with_inputbar")

        # 12) 关闭菜单，查看空画布 + 4 节点整体
        page.keyboard.press("Escape")
        page.mouse.move(0, 0)
        page.wait_for_timeout(400)
        shot(page, "14_all_four_nodes")

        # 13) 点击 Beta 标签（3D世界）作为次级菜单项验证
        page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2 - 200)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        page.wait_for_timeout(300)
        shot(page, "15_menu_show_beta_tags")

        # 14) 截图汇总：hover text 节点触发浮动工具条（H1-H3/B/I）
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        text_nodes.first.click()
        page.wait_for_timeout(300)
        page.locator('.react-flow__node[data-kind="text"]').first.locator(".pea-node-text-edit").click()
        page.wait_for_timeout(300)
        shot(page, "16_text_with_text_toolbar")

        browser.close()

    print(f"\nTOTAL console errors/warnings: {len(errors)}")
    for e in errors[:20]:
        print("  ", e)

    return 0 if not any("error:" in e or "pageerror" in e for e in errors) else 1


if __name__ == "__main__":
    sys.exit(main())