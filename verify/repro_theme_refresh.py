"""复现并验证：画布暗系主题刷新后是否保持。
步骤：
1. 注册登录
2. 进入画布（自动创建画布）
3. 切到暗系主题（runway）
4. 记录 html class / body data-surface / 截图
5. 刷新页面
6. 再次记录 html class / body data-surface / 截图
7. 对比判断修复是否成功
"""

from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SHOTS = Path("D:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

errors: list[str] = []


def on_console(msg):
    if msg.type == "error":
        errors.append(f"{msg.type}: {msg.text}")


def on_pageerror(err):
    errors.append(f"pageerror: {err}")


def snap(page, name: str):
    p = SHOTS / f"theme_refresh_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"[shot] {p}")


def read_theme_state(page):
    return page.evaluate(
        """() => ({
            htmlClasses: document.documentElement.className,
            bodySurface: document.body.dataset.surface,
            creatorDesign: localStorage.getItem('pea_creator_design'),
            peaTheme: localStorage.getItem('pea_theme'),
            route: localStorage.getItem('pea_ui_route'),
        })"""
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(800)

        # 注册
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"theme_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "Theme")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_timeout(2000)
        print("[state] after login:", read_theme_state(page))
        snap(page, "01_after_login")

        # 若没自动进画布，从工作空间新建项目
        if page.locator(".react-flow__viewport").count() == 0:
            print("[info] not in canvas, creating new project...")
            page.locator("button", has_text="新建项目").first.click()
            page.wait_for_timeout(2000)
            page.wait_for_selector(".react-flow__viewport", timeout=15000)

        # 切到暗系主题：先切到 figma 再切到 runway，确保 onChange 触发并写入 localStorage
        page.locator(".pea-canvas-theme-select").first.click()
        page.wait_for_timeout(400)
        page.locator(".ant-select-item", has_text="明亮创作").first.click()
        page.wait_for_timeout(800)
        page.locator(".pea-canvas-theme-select").first.click()
        page.wait_for_timeout(400)
        page.locator(".ant-select-item", has_text="暗调电影感").first.click()
        page.wait_for_timeout(800)

        print("[state] after switch to runway:", read_theme_state(page))
        snap(page, "02_runway_before_refresh")

        # 刷新
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        print("[state] after refresh:", read_theme_state(page))
        snap(page, "03_runway_after_refresh")

        # 判断
        state = read_theme_state(page)
        html_has_dark = "dark" in state["htmlClasses"].split()
        html_has_light = "light" in state["htmlClasses"].split()
        body_surface = state["bodySurface"]
        creator_design = state["creatorDesign"]

        print("\n=== RESULT ===")
        print(f"html dark: {html_has_dark}, html light: {html_has_light}")
        print(f"body[data-surface]: {body_surface}")
        print(f"localStorage pea_creator_design: {creator_design}")
        print(f"console/page errors: {errors}")

        ok = html_has_dark and not html_has_light and body_surface == "cinematic" and creator_design == "runway"
        print(f"PASS: {ok}")

        browser.close()
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
