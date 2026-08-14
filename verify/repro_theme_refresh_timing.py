"""精细化复现：刷新后观察 html class / body surface 的时序变化。"""

from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SHOTS = Path("D:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)


def read_theme_state(page):
    return page.evaluate(
        """() => ({
            htmlClasses: document.documentElement.className,
            bodySurface: document.body.dataset.surface,
        })"""
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(800)

        # 注册
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"tt_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "TT")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)

        if page.locator(".react-flow__viewport").count() == 0:
            page.locator("button", has_text="新建项目").first.click()
            page.wait_for_timeout(2000)

        # 切到 runway 并确保写入 localStorage
        page.locator(".pea-canvas-theme-select").first.click()
        page.wait_for_timeout(400)
        page.locator(".ant-select-item", has_text="明亮创作").first.click()
        page.wait_for_timeout(800)
        page.locator(".pea-canvas-theme-select").first.click()
        page.wait_for_timeout(400)
        page.locator(".ant-select-item", has_text="暗调电影感").first.click()
        page.wait_for_timeout(800)

        print("before refresh:", read_theme_state(page))

        # 刷新并在多个时间点采样
        page.reload(wait_until="networkidle")
        for i in range(30):
            page.wait_for_timeout(100)
            st = read_theme_state(page)
            print(f"  t={i*100}ms: {st}")

        page.screenshot(path=str(SHOTS / "theme_refresh_timing.png"), full_page=False)
        browser.close()


if __name__ == "__main__":
    main()
