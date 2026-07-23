"""E11 · 画布视觉细节对齐 pea-canvas-v12.html
- 画布点阵背景（.react-flow__background-pattern.dots 可见）
- 左侧工具栏 6 个图标（➕/🔍/📁/⊞/💬/🕐）
- 节点 footer tag（Image/Generate/...）
- 底部 Composer 输入条（add-pal）
- Composer 输入 → 节点 +1
- 顶部「免费体验」按钮
- 0 console error
"""
import os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:8088"
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)


def main():
    fails = []
    console_errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: console_errors.append(f"pageerror:{e}"))
        page.on("console", lambda m: m.type == "error" and console_errors.append(f"console:{m.text}"))

        # 登录
        page.goto(f"{BASE}/", wait_until="networkidle")
        page.wait_for_timeout(500)
        if "login" in page.url or page.locator('input[placeholder*="pea.ai"]').count() > 0:
            page.locator('input[placeholder*="pea.ai"]').fill("verify@pea.ai")
            page.locator('input[type="password"]').fill("password123")
            page.locator('form button[type="submit"]').click()
            page.wait_for_url(lambda u: "login" not in u, timeout=10_000)
        page.wait_for_timeout(1500)

        # 进入画布
        page.get_by_text("工作空间", exact=True).first.click()
        page.wait_for_timeout(1200)

        # 1) 画布点阵背景（ReactFlow 用 <pattern><circle/> 渲染 dots，无 class 标识）
        bg = page.locator(".react-flow__background").first
        if bg.count() == 0:
            fails.append("画布背景 .react-flow__background 缺失")
        else:
            circles = bg.locator("pattern circle")
            if circles.count() == 0:
                fails.append("画布点阵 pattern 内无 circle 元素（dots 缺失）")
            else:
                print(f"PASS 画布点阵背景（{circles.count()} 个圆点）")

        page.screenshot(path=SHOTS / "e11_01_canvas_overview.png", full_page=False)

        # 2) 左侧工具栏 6 个图标（限定 .pea-toolbar 容器避免命中 Composer 里的同名按钮）
        toolbar = page.locator(".pea-toolbar")
        if toolbar.count() == 0:
            fails.append("左侧工具栏 .pea-toolbar 缺失")
        else:
            checks = {
                "添加节点（双击画布也可打开）": "➕",
                "搜索": "🔍",
                "文件": "📁",
                "节点库": "⊞",
                "评论": "💬",
                "历史记录": "🕐",
            }
            for aria_label, emoji in checks.items():
                btn = toolbar.get_by_role("button", name=aria_label, exact=True)
                if btn.count() == 0:
                    fails.append(f"左侧工具栏缺少按钮: {aria_label}")
                else:
                    print(f"PASS 左侧工具栏按钮: {aria_label} ({emoji})")
        page.screenshot(path=SHOTS / "e11_02_left_toolbar.png", full_page=False)

        # 3) 添加一个生成节点，再检查节点 footer tag
        toolbar.get_by_role("button", name="添加节点（双击画布也可打开）", exact=True).first.click()
        page.wait_for_timeout(500)
        page.get_by_role("button", name="生成", exact=True).first.click()
        page.wait_for_timeout(800)
        nodes_after = page.locator(".pea-node").count()
        print(f"INFO 节点数 = {nodes_after}")
        if nodes_after < 1:
            fails.append("从库添加生成节点后节点数为 0")
        # 节点 footer tag
        footer_tag = page.locator(".pea-node .pea-node-tag").first
        if footer_tag.count() == 0:
            fails.append("节点底部 .pea-node-tag 缺失")
        else:
            print(f"PASS 节点 footer tag: {footer_tag.inner_text()}")
        page.screenshot(path=SHOTS / "e11_03_node_with_tag.png", full_page=False)

        # 4) 底部 Composer 存在
        composer = page.locator(".pea-composer")
        if composer.count() == 0:
            fails.append("底部 Composer .pea-composer 缺失")
        else:
            print("PASS 底部 Composer 存在")
            page.screenshot(path=SHOTS / "e11_04_composer.png", full_page=False)

        # 5) Composer 输入 → 添加节点
        before = page.locator(".pea-node").count()
        ta = page.locator(".pea-composer-input").first
        ta.click()
        ta.fill("测试 composer 输入：一只赛博朋克机器人在霓虹街道")
        page.wait_for_timeout(200)
        page.locator(".pea-composer-send").first.click(force=True)
        page.wait_for_timeout(800)
        after = page.locator(".pea-node").count()
        if after != before + 1:
            fails.append(f"Composer 发送后节点数 {before} -> {after}（期望 +1）")
        else:
            print(f"PASS Composer 发送 {before} -> {after} 节点 +1")
        page.screenshot(path=SHOTS / "e11_05_composer_after_send.png", full_page=False)

        # 6) 顶部「免费体验」按钮
        trial = page.get_by_role("button", name="免费体验", exact=True)
        if trial.count() == 0:
            fails.append("顶部「免费体验」按钮缺失")
        else:
            print("PASS 顶部「免费体验」按钮存在")
            trial.first.click()
            page.wait_for_timeout(500)

        # 7) 切到浅色再截一张对照
        page.locator(".pea-topnav .ant-segmented-item-label", has_text="浅").first.click()
        page.wait_for_timeout(500)
        page.screenshot(path=SHOTS / "e11_06_light_theme.png", full_page=False)
        # 切回深色
        page.locator(".pea-topnav .ant-segmented-item-label", has_text="深").first.click()
        page.wait_for_timeout(500)

        browser.close()

    if console_errors:
        print("\nCONSOLE ERRORS:")
        for e in console_errors:
            print(" -", e)
        fails.append(f"console errors: {len(console_errors)}")

    print("\n=========== RESULT ===========")
    if fails:
        for f in fails:
            print("FAIL:", f)
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED, 0 console error")


if __name__ == "__main__":
    main()
