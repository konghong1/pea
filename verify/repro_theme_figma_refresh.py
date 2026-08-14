"""验证 figma 亮系主题刷新后是否保持。"""

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
            creatorDesign: localStorage.getItem('pea_creator_design'),
        })"""
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(800)

        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"fig_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "Fig")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)

        if page.locator(".react-flow__viewport").count() == 0:
            page.locator("button", has_text="新建项目").first.click()
            page.wait_for_timeout(2000)

        # 切到 figma
        page.locator(".pea-canvas-theme-select").first.click()
        page.wait_for_timeout(400)
        page.locator(".ant-select-item", has_text="明亮创作").first.click()
        page.wait_for_timeout(800)

        print("before refresh:", read_theme_state(page))
        page.screenshot(path=str(SHOTS / "theme_figma_before.png"), full_page=False)

        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2000)

        print("after refresh:", read_theme_state(page))
        page.screenshot(path=str(SHOTS / "theme_figma_after.png"), full_page=False)

        browser.close()


if __name__ == "__main__":
    main()
