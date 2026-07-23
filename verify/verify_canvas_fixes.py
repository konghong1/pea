"""验证本次画布三处修复：
1. 左下角画布控件胶囊符合截图 #1（地图/网格/适配/滑块/帮助）。
2. 节点缩放不影响弹出的输入框与文本工具条（fixed 视口定位）。
3. 连线未命中节点时弹出截图 #3 的节点选择菜单；选择后创建节点并连接，且源节点不消失。
硬标准：0 console error。
"""

from playwright.sync_api import sync_playwright, expect
from pathlib import Path
import time

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

errors: list[str] = []
console_msgs: list[str] = []


def on_console(msg):
    if msg.type == "error":
        errors.append(f"{msg.type}: {msg.text}")
    console_msgs.append(f"[{msg.type}] {msg.text}")


def on_pageerror(err):
    errors.append(f"pageerror: {err}")


def shot(page, name: str):
    p = SHOTS / f"cf_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"[shot] {p}")


def parse_scale(page):
    """从 react-flow__viewport 的 transform 中解析当前缩放比例。"""
    return page.evaluate(
        """() => {
            const el = document.querySelector('.react-flow__viewport');
            if (!el) return 1;
            const m = el.style.transform.match(/scale\\(([^)]+)\\)/);
            return m ? parseFloat(m[1]) : 1;
        }"""
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        # 注册并进入画布
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"cf_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "CF")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        shot(page, "01_default")

        # ============ 1. 画布控件 ============
        controls = page.locator(".pea-canvas-controls")
        expect(controls).to_be_visible()
        print(f"[check] canvas controls visible: True")
        for cls, name in [
            (".pea-canvas-controls-btn", "map/grid/fit buttons"),
            ("input[type='range']", "zoom slider"),
            (".pea-canvas-controls-help", "help button"),
        ]:
            el = controls.locator(cls).first
            expect(el).to_be_visible()
            print(f"[check] {name} visible: True")
        shot(page, "02_controls")

        # 点击适配视图按钮不应报错
        controls.locator("button[title='适配视图 (F)']").click()
        page.wait_for_timeout(500)
        print(f"[check] fit-view clicked ok")

        # ============ 2. 添加 text 节点，验证输入框与文本工具条 ============
        page.locator(".pea-toolbar").get_by_role(
            "button", name="添加节点（双击画布也可打开）", exact=True
        ).first.click()
        page.wait_for_timeout(800)
        page.locator(".pea-add-menu-item", has_text="文本").first.click()
        page.wait_for_timeout(800)
        shot(page, "03_text_node_added")

        node = page.locator(".react-flow__node").first
        node_box = node.bounding_box()
        prompt = page.locator(".node-chat-prompt")
        expect(prompt).to_be_visible()
        prompt_box = prompt.bounding_box()
        toolbar = page.locator(".text-node-toolbar")
        expect(toolbar).to_be_visible()
        toolbar_box = toolbar.bounding_box()
        print(f"[check] node-chat-prompt visible: True")
        print(f"[check] text-node-toolbar visible: True")
        print(
            f"[check] prompt below node: {prompt_box['y'] >= node_box['y'] + node_box['height'] - 5}"
        )
        print(
            f"[check] toolbar above node: {toolbar_box['y'] + toolbar_box['height'] <= node_box['y'] + 22}"
        )
        shot(page, "04_prompt_and_toolbar")

        # 通过滑块缩放画布，输入框仍应锚定在节点下方且不跟随缩放变形
        zoom_before = parse_scale(page)
        print(f"[check] zoom before slider: {zoom_before:.2f}")
        slider = controls.locator("input[type='range']").first
        slider_box = slider.bounding_box()
        # 把滑块拖到 25% 位置（缩小）
        page.mouse.move(slider_box["x"] + slider_box["width"] * 0.25, slider_box["y"] + slider_box["height"] / 2)
        page.mouse.down()
        page.mouse.up()
        page.wait_for_timeout(800)
        zoom_after = parse_scale(page)
        print(f"[check] zoom after slider: {zoom_after:.2f} (should be smaller)")
        shot(page, "05_after_zoom_out")

        prompt_box2 = prompt.bounding_box()
        node_box2 = node.bounding_box()
        print(
            f"[check] prompt still below node after zoom: {prompt_box2['y'] >= node_box2['y'] + node_box2['height'] - 10}"
        )
        print(
            f"[check] prompt width stable: before={prompt_box['width']:.0f} after={prompt_box2['width']:.0f}"
        )

        # ============ 3. 连线未命中时弹出节点选择菜单 ============
        # 取消选中以便从源节点拖线
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        # 直接通过 source handle 拖线到空白处
        source_handle = page.locator(".react-flow__node .react-flow__handle[data-handlepos='right']").first
        hb = source_handle.bounding_box()
        if hb:
            start_x = hb["x"] + hb["width"] / 2
            start_y = hb["y"] + hb["height"] / 2
            end_x = start_x + 280
            end_y = start_y + 80
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(end_x, end_y, steps=10)
            page.mouse.up()
            page.wait_for_timeout(500)
            shot(page, "06_edge_drop_menu")

            edge_menu = page.locator(".pea-edge-menu")
            visible = edge_menu.count() > 0 and edge_menu.is_visible()
            print(f"[check] edge-node menu opened on dangling connection: {visible}")
            if visible:
                # 选择图片生成
                edge_menu.locator(".pea-edge-menu-item", has_text="图片生成").first.click()
                page.wait_for_timeout(800)
                shot(page, "07_image_node_created")
                node_count = page.locator(".react-flow__node").count()
                edge_count = page.locator(".react-flow__edge").count()
                print(f"[check] nodes count after edge drop pick: {node_count} (expected 2)")
                print(f"[check] edges count after edge drop pick: {edge_count} (expected 1)")
            else:
                errors.append("edge-node menu did not open on dangling connection")
        else:
            errors.append("source handle not found")

        # ============ 4. 直接连接两个现有节点，源节点不应消失 ============
        # 已有 2 个节点，从第一个拖到第二个 target handle
        nodes = page.locator(".react-flow__node").all()
        if len(nodes) >= 2:
            src = nodes[0]
            tgt = nodes[1]
            src_h = src.locator(".react-flow__handle[data-handlepos='right']").bounding_box()
            tgt_h = tgt.locator(".react-flow__handle[data-handlepos='left']").bounding_box()
            if src_h and tgt_h:
                page.mouse.move(src_h["x"] + src_h["width"] / 2, src_h["y"] + src_h["height"] / 2)
                page.mouse.down()
                page.mouse.move(tgt_h["x"] + tgt_h["width"] / 2, tgt_h["y"] + tgt_h["height"] / 2, steps=10)
                page.mouse.up()
                page.wait_for_timeout(500)
                node_count_after = page.locator(".react-flow__node").count()
                print(f"[check] nodes count after direct connect: {node_count_after} (should be 2)")
                shot(page, "08_direct_connect")

        # ============ 总结 ============
        print(f"\n[TOTAL console errors]: {len(errors)}")
        for e in errors:
            print(f"  - {e}")
        log = SHOTS.parent / "canvas_fixes_verify.log"
        log.write_text(
            f"timestamp={ts}\nerrors={len(errors)}\nconsole={len(console_msgs)}\n"
            + "\n".join(errors)
            + "\n--- last 30 console ---\n"
            + "\n".join(console_msgs[-30:]),
            encoding="utf-8",
        )
        browser.close()
        if errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
