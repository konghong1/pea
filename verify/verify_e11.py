"""E11 · 画布视觉细节对齐 pea-canvas-v12.html（对齐当前 UI，2026-07-24 重写）

覆盖：
- 画布点阵背景（.react-flow__background 内 pattern/circle 渲染 dots）
- 左侧工具栏 6 个图标按钮（➕添加节点 / 🔍搜索 / 📁文件 / ⊞节点库 / 💬评论 / 🕐历史记录）
- 添加「文本」节点后，节点顶部 tag-pill 显示正确 kind 标签（Text）
- 顶部「免费体验」按钮
- 深 / 浅 主题切换
- 0 console error（硬标准）

移除项（画布重设计已删除，非缺陷）：
- 底部 Composer 输入条与「Composer 发送→节点+1」——已被 NodeChatPrompt 浮动输入框取代。
- 节点底部 footer tag——标签已移到节点顶部（.pea-node-tag-pill）。
"""
import os
import sys
import uuid
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)
EMAIL = f"e11_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
fails = []
console_errors = []


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


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: console_errors.append(f"pageerror:{e}"))
        page.on("console", lambda m: m.type == "error" and console_errors.append(f"console:{m.text}"))

        # 注册并进入画布
        page.goto(f"{BASE}/", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', EMAIL)
        page.fill('input[placeholder="至少 8 位"]', PW)
        page.fill('input[placeholder="可选"]', "E11Bot")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        ensure_canvas(page)
        page.wait_for_timeout(800)

        # 1) 画布点阵背景
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

        # 2) 左侧工具栏 6 个图标按钮
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
            for aria_label in checks:
                btn = toolbar.get_by_role("button", name=aria_label, exact=True)
                if btn.count() == 0:
                    fails.append(f"左侧工具栏缺少按钮: {aria_label}")
                else:
                    print(f"PASS 左侧工具栏按钮: {aria_label}")
        page.screenshot(path=SHOTS / "e11_02_left_toolbar.png", full_page=False)

        # 3) 添加「文本」节点，验证顶部 tag-pill
        toolbar.get_by_role("button", name="添加节点（双击画布也可打开）", exact=True).first.click()
        page.wait_for_timeout(500)
        page.locator(".pea-add-menu").get_by_text("文本", exact=True).first.click()
        page.wait_for_timeout(800)
        nodes_after = page.locator(".pea-node").count()
        print(f"INFO 节点数 = {nodes_after}")
        if nodes_after < 1:
            fails.append("从库添加文本节点后节点数为 0")
        pill = page.locator(".pea-node .pea-node-tag-pill").first
        if pill.count() == 0:
            fails.append("节点顶部标签 .pea-node-tag-pill 缺失")
        else:
            txt = pill.inner_text()
            if "Text" not in txt:
                fails.append(f"节点 tag-pill 文本异常: {txt!r}")
            else:
                print(f"PASS 节点顶部 tag-pill: {txt!r}")
        page.screenshot(path=SHOTS / "e11_03_node_with_tag.png", full_page=False)

        # 4) 顶部「免费体验」按钮
        trial = page.get_by_role("button", name="免费体验", exact=True)
        if trial.count() == 0:
            fails.append("顶部「免费体验」按钮缺失")
        else:
            print("PASS 顶部「免费体验」按钮存在")
            trial.first.click()
            page.wait_for_timeout(500)

        # 5) 浅 / 深 主题切换
        page.locator(".pea-topnav .ant-segmented-item-label", has_text="浅").first.click()
        page.wait_for_timeout(500)
        is_light = "dark" not in (page.evaluate("document.documentElement.className") or "")
        if not is_light:
            fails.append("切换浅色主题未生效")
        else:
            print("PASS 浅色主题生效")
        page.screenshot(path=SHOTS / "e11_06_light_theme.png", full_page=False)
        page.locator(".pea-topnav .ant-segmented-item-label", has_text="深").first.click()
        page.wait_for_timeout(500)
        is_dark = "dark" in (page.evaluate("document.documentElement.className") or "")
        if not is_dark:
            fails.append("切换深色主题未生效")
        else:
            print("PASS 深色主题生效")

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
        sys.exit(0)


if __name__ == "__main__":
    main()
