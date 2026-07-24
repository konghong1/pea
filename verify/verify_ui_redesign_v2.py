"""验证画布 UI 重设计 v2：
- 副驾驶聊天侧边栏固定在屏幕最右侧 (380px)
- 移除画布右侧 Inspector（"选中一个节点以查看 / 编辑属性" 没了）
- 节点选中时正下方浮现 node-chat-prompt
- 收起态为右下角圆形气泡
- 0 console error
"""

from playwright.sync_api import sync_playwright
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
    p = SHOTS / f"uir2_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"[shot] {p}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(800)
        # 注册新用户
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"v2_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "V2")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(5000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        # ============ 场景 1：默认空画布 ============
        # 检查聊天面板是否存在（应为收起态 = 气泡）
        bubble = page.locator(".pea-agent-bubble")
        panel = page.locator(".pea-agent-panel")
        print(f"[check] chat bubble visible (collapsed): {bubble.count() > 0}")
        print(f"[check] chat panel visible (expanded): {panel.count() > 0}")
        # 检查 Inspector 已被移除（"选中一个节点..." 文字不再出现）
        placeholder = page.locator("text=选中一个节点以查看")
        print(f"[check] inspector placeholder removed: {placeholder.count() == 0}")
        # 收起态截图
        shot(page, "01_default_collapsed_bubble")

        # ============ 场景 2：点击气泡展开聊天面板 ============
        bubble.first.click()
        page.wait_for_timeout(500)
        panel = page.locator(".pea-agent-panel")
        panel_box = panel.bounding_box()
        print(f"[check] panel expanded: {panel.count() > 0}")
        # 校验 panel 在最右侧
        vw = 1440
        if panel_box:
            right_gap = vw - (panel_box["x"] + panel_box["width"])
            print(
                f"[check] panel right edge gap: {right_gap:.1f}px (should be ~0)"
            )
            print(f"[check] panel width: {panel_box['width']:.1f}px (should be ~380)")
            print(f"[check] panel left: {panel_box['x']:.1f}px")
        shot(page, "02_chat_panel_right")

        # ============ 场景 3：添加一个 generate 节点 ============
        page.locator(".pea-toolbar").get_by_role(
            "button", name="添加节点（双击画布也可打开）", exact=True
        ).first.click()
        page.wait_for_timeout(500)
        page.locator(".pea-add-menu").get_by_text("图片", exact=True).first.click()
        page.wait_for_timeout(800)

        # 此时节点被默认选中 — node-chat-prompt 应出现
        chat_prompt = page.locator(".node-chat-prompt")
        print(f"[check] node-chat-prompt visible (node selected): {chat_prompt.count() > 0}")
        if chat_prompt.count() > 0:
            cp_box = chat_prompt.first.bounding_box()
            node_box = page.locator(".react-flow__node").first.bounding_box()
            print(
                f"[check] chat-prompt top {cp_box['y']:.0f} > node bottom {node_box['y'] + node_box['height']:.0f}: "
                f"{cp_box['y'] > node_box['y'] + node_box['height'] - 5}"
            )
            print(
                f"[check] chat-prompt left {cp_box['x'] + cp_box['width']/2:.0f} ≈ node center "
                f"{node_box['x'] + node_box['width']/2:.0f}"
            )
        shot(page, "03_node_chat_prompt_below")

        # ============ 场景 4：在 node-chat-prompt 中输入并发送 ============
        prompt_input = page.locator(".node-chat-prompt-input").first
        prompt_input.fill("帮我写一段赛博朋克风格的提示词")
        page.wait_for_timeout(200)
        shot(page, "04_chat_prompt_typing")
        page.locator(".node-chat-prompt-send").first.click()
        page.wait_for_timeout(800)
        # 验证：聊天面板中出现了这条消息
        msgs = page.locator(".pea-agent-msg.user")
        print(f"[check] chat message pushed: {msgs.count() >= 1}")
        shot(page, "05_chat_prompt_sent")

        # ============ 场景 5：取消选中（按 Escape） ============
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        cp_after = page.locator(".node-chat-prompt")
        print(f"[check] chat-prompt hidden after escape: {cp_after.count() == 0}")
        shot(page, "06_escape_deselect")

        # ============ 场景 6：再选一个 text 节点，验证浮动文本工具条 + 浮动聊天框都出现 ============
        page.locator(".pea-toolbar").get_by_role(
            "button", name="添加节点（双击画布也可打开）", exact=True
        ).first.click()
        page.wait_for_timeout(500)
        page.locator(".pea-add-menu").get_by_text("文本", exact=True).first.click()
        page.wait_for_timeout(800)
        shot(page, "07_text_node_selected")

        # ============ 总结 ============
        print(f"\n[TOTAL console errors]: {len(errors)}")
        for e in errors:
            print(f"  - {e}")
        # 写一份日志
        log = SHOTS.parent / "uir2_verify.log"
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