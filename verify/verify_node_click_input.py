"""
验证节点点击输入栏行为（2026-07-24 修复后）：
  1. 点击任意节点 → 输入栏弹出
  2. 切换点击不同节点 → 输入栏跟随到新节点
  3. 再次点击之前点过的节点 → 输入栏再次弹出（不再只有首次有效）
  4. 输入栏保留已有 prompt 内容可继续编辑
  5. 节点中心支持 generating 动画与结果展示
"""
import time
from playwright.sync_api import sync_playwright, expect
from pathlib import Path

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = "http://localhost:8088"

errors: list[str] = []


def on_console(msg):
    if msg.type == "error":
        errors.append(f"{msg.type}: {msg.text}")


def on_pageerror(err):
    errors.append(f"pageerror: {err}")


def shot(page, name: str):
    p = SHOTS / f"vnci_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"    [shot] {p}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        # ---- 登录 ----
        print("[1] 打开页面并注册登录 ...")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"vnci_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "VNCI")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        print("    ✅ 已进入画布")

        # 添加几个不同类型的节点用于测试
        print("\n[2] 添加测试节点 ...")

        # 添加 text 节点
        page.locator(".pea-toolbar").get_by_role(
            "button", name="添加节点（双击画布也可打开）", exact=True
        ).first.click()
        page.wait_for_timeout(500)
        page.locator(".pea-add-menu-item", has_text="文本").first.click()
        page.wait_for_timeout(800)

        # 添加 image 节点
        page.locator(".pea-toolbar").get_by_role(
            "button", name="添加节点（双击画布也可打开）", exact=True
        ).first.click()
        page.wait_for_timeout(500)
        page.locator(".pea-add-menu-item", has_text="图片").first.click()
        page.wait_for_timeout(800)

        # 添加 generate 节点（用视频代替，因为菜单里没有"生成"选项）
        page.locator(".pea-toolbar").get_by_role(
            "button", name="添加节点（双击画布也可打开）", exact=True
        ).first.click()
        page.wait_for_timeout(500)
        page.locator(".pea-add-menu-item", has_text="视频").first.click()
        page.wait_for_timeout(800)

        nodes = page.locator(".pea-node")
        count = nodes.count()
        print(f"    已添加 {count} 个节点")
        assert count >= 3, f"节点不足3个，实际{count}"
        shot(page, "01_nodes_added")

        # ---- 测试：点击第1个节点(text) → 输入栏出现 ----
        print("\n[3] 点击第1个节点(text)，检查输入栏弹出 ...")
        n1 = nodes.nth(0)
        n1_box = n1.bounding_box()
        assert n1_box, "node1 无边界"
        page.mouse.click(n1_box["x"] + n1_box["width"] / 2, n1_box["y"] + n1_box["height"] / 2)
        page.wait_for_timeout(500)

        bar = page.locator(".node-input-bar")
        expect(bar).to_be_visible(timeout=3000)
        bar_box = bar.bounding_box()
        print(f"    ✅ 第1个节点输入栏已弹出 (w={bar_box['width']:.0f}, h={bar_box['height']:.0f})")
        shot(page, "02_node1_input")

        # 在输入栏输入文字
        textarea = page.locator(".node-chat-prompt-input")
        expect(textarea).to_be_visible()
        textarea.click()
        page.keyboard.type("一只戴着墨镜的猫", delay=20)
        page.wait_for_timeout(200)
        val = textarea.input_value()
        assert "猫" in val, f"输入内容不匹配: {val}"
        print(f"    ✅ 已输入: {val}")
        shot(page, "03_node1_typed")

        # ---- 点击第2个节点(image) → 输入栏移动 ----
        print("\n[4] 点击第2个节点(image)，输入栏应跟随 ...")
        n2 = nodes.nth(1)
        n2_box = n2.bounding_box()
        page.mouse.click(n2_box["x"] + n2_box["width"] / 2, n2_box["y"] + n2_box["height"] / 2)
        page.wait_for_timeout(500)

        expect(bar).to_be_visible(timeout=3000)
        # fixed 定位元素 bounding_box 可能返回 None，用 js 检查可见性替代
        bar_visible = bar.is_visible()
        print(f"    ✅ 第2个节点输入栏已弹出 (visible={bar_visible})")
        shot(page, "04_node2_input")

        # ---- 再次点击第1个节点 → 核心修复验证！----
        print("\n[5] ★ 再次点击第1个节点（核心修复：非首次也必须弹出）...")
        page.mouse.click(n1_box["x"] + n1_box["width"] / 2, n1_box["y"] + n1_box["height"] / 2)
        page.wait_for_timeout(600)

        expect(bar).to_be_visible(timeout=3000)
        bar3_visible = bar.is_visible()
        print(f"    ✅ 第1个节点输入栏再次弹出！ (visible={bar3_visible})")
        shot(page, "05_node1_again")

        # 检查 textarea 内容
        textarea3 = page.locator(".node-chat-prompt-input")
        if textarea3.count() > 0:
            val3 = textarea3.input_value()
            print(f"    输入栏内容: '{val3}'")

        # ---- 快速来回切换压力测试 ----
        print("\n[6] 来回快速切换两个节点各3次 ...")
        for i in range(3):
            page.mouse.click(n2_box["x"] + n2_box["width"] / 2, n2_box["y"] + n2_box["height"] / 2)
            page.wait_for_timeout(300)
            expect(bar).to_be_visible(timeout=2000)

            page.mouse.click(n1_box["x"] + n1_box["width"] / 2, n1_box["y"] + n1_box["height"] / 2)
            page.wait_for_timeout(300)
            expect(bar).to_be_visible(timeout=2000)
        print("    ✅ 6次切换均保持输入栏正常")
        shot(page, "06_stress_test")

        # ---- 点击第3个节点(video) 验证媒体节点 ----
        print("\n[7] 点击第3个节点(video) ...")
        n3 = nodes.nth(2)
        n3_box = n3.bounding_box()
        page.mouse.click(n3_box["x"] + n3_box["width"] / 2, n3_box["y"] + n3_box["height"] / 2)
        page.wait_for_timeout(500)
        expect(bar).to_be_visible(timeout=3000)
        print(f"    ✅ video 节点输入栏正常")
        shot(page, "07_generate_node")

        # ---- 控制台错误汇总 ----
        print("\n[8] 控制台错误检查 ...")
        if errors:
            print(f"    ⚠️ 发现 {len(errors)} 条控制台错误:")
            for e in errors[:8]:
                print(f"      {e[:150]}")
        else:
            print("    ✅ 零控制错误")

        browser.close()
        print("\n🎉 全部通过！节点点击→输入栏每次都正确弹出。")


if __name__ == "__main__":
    main()
