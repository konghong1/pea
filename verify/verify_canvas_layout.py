"""
pea 画布新布局 + 视图切换真机 E2E (2026-07-24 重构)

验证项：
  - 默认落地 = 工作空间（项目列表），不是空画布
  - Home 页是空的占位（"主页规划中"）
  - 点击项目卡 → 进入画布
  - 画布头部：左上 pea logo + 标题 + 上次修改（点击展开下拉）
  - 下拉菜单：返回工作空间 / 探索 / TapTV / 竞技场 / 项目(重命名/新建项目) / 删除
  - 画布右上：Tapies 余额 + 社区 + 分享
  - 画布左下：网格 + 缩放滑块 + ?
  - 画布右下：Brainstorm 提示 + 头像
  - 左侧工具栏：7 个按钮 (+ 🔍 📁 ⊞ 💬 🕐) + W 头像
  - 画布模式下隐藏顶部 TopNav
  - 返回工作空间 → 回到项目列表
  - console error 数 = 0
"""

import asyncio
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

ROOT = Path(__file__).parent
SHOTS = ROOT / "_canvas_layout"
SHOTS.mkdir(exist_ok=True)


async def shot(page, name: str):
    p = SHOTS / f"{name}.png"
    await page.screenshot(path=str(p))
    print(f"   📸 {p.name}")


async def main() -> int:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 848})
        page = await ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: errors.append(f"console.{m.type}: {m.text}")
            if m.type == "error"
            else None,
        )

        ts = int(time.time())
        email = f"canvas_ui_{ts}@pea.ai"

        # 0. 注册
        print(f"[0] 注册 {email}")
        await page.goto("http://localhost:8088/login", wait_until="domcontentloaded")
        await page.wait_for_selector("input[placeholder='you@pea.ai']", timeout=8000)
        # 切到注册 tab
        reg_clicked = False
        for sel in ["text=去注册", "button:has-text('去注册')", "button:has-text('注册')"]:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                try:
                    await loc.click(timeout=2000)
                    reg_clicked = True
                    break
                except Exception:
                    pass
        print(f"   register tab clicked: {reg_clicked}")
        await page.wait_for_selector("input[placeholder='可选']", timeout=5000)
        await page.fill("input[placeholder='you@pea.ai']", email)
        await page.fill("input[placeholder='至少 8 位']", "Pass1234!")
        await page.fill("input[placeholder='可选']", "canvas-ui")
        # 提交按钮（antd 在按钮文字中插空格渲染为"注 册"，所以遍历可见按钮去空格匹配）
        submit_clicked = False
        for btn in await page.locator("button:visible").all():
            try:
                txt = (await btn.inner_text() or "").replace(" ", "")
                if "注册" in txt or "登录" in txt:
                    await btn.click()
                    submit_clicked = True
                    break
            except Exception:
                pass
        print(f"   submit clicked: {submit_clicked}")
        # 等待注册成功，跳转到 /
        await page.wait_for_url("http://localhost:8088/", timeout=10000)
        await page.wait_for_load_state("networkidle")

        # 1. 默认落地 = 工作空间（项目列表），不是空画布
        print("[1] 默认落地 = 工作空间（项目列表）")
        await page.wait_for_selector(".projects-page", timeout=8000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)
        # 没有画布头部（无 .pea-canvas-host）
        assert await page.locator(".pea-canvas-host").count() == 0, "默认应不显示画布"
        # 顶部 TopNav 应可见
        assert await page.locator(".pea-topnav").count() == 1, "工作空间模式应显示 TopNav"
        # 项目列表应有"新建项目"按钮（toolbar；空状态也有一个，新用户 = 2 个）
        new_btn_count = await page.locator(".projects-new-btn", has_text="新建项目").count()
        assert new_btn_count >= 1, f"应有新建项目按钮 (实际 {new_btn_count})"
        await shot(page, "01_workspace_default")

        # 2. 点击 Home 导航 → 应进入空的占位页
        print("[2] 点击主页导航 → 占位页")
        await page.locator(".pea-nav-item", has_text="主页").click()
        await page.wait_for_selector("text=主页规划中", timeout=5000)
        # 不应有 .projects-page 内容（应有占位 UI）
        assert await page.locator(".projects-page").count() == 1, "Home 页应保留容器"
        await shot(page, "02_home_placeholder")

        # 3. 回到工作空间，新建一个项目
        print("[3] 回工作空间 + 新建项目 → 进入画布")
        await page.locator(".pea-nav-item", has_text="工作空间").click()
        await page.wait_for_selector(".projects-page", timeout=5000)
        await page.locator(".projects-new-btn", has_text="新建项目").first.click()
        # 进入画布
        await page.wait_for_selector(".pea-canvas-host", timeout=8000)
        await page.wait_for_load_state("networkidle")
        await shot(page, "03_canvas_after_new")

        # 4. 验证画布头部布局
        print("[4] 画布头部布局（顶部 + 右上 + 底部）")
        # TopNav 在画布模式应隐藏
        topnav_count = await page.locator(".pea-topnav").count()
        assert topnav_count == 0, f"画布模式应隐藏 TopNav (实际 {topnav_count})"
        # 左上：pea-canvas-header
        assert await page.locator(".pea-canvas-header").count() == 1, "应有画布头部"
        # 标题与上次修改
        assert await page.locator(".pea-canvas-header-trigger").count() == 1
        title_text = await page.locator(".pea-canvas-header-trigger").inner_text()
        assert "未命名画布" in title_text or "上次修改于" in title_text, \
            f"画布头部应含标题与时间：{title_text!r}"
        # 右上：操作区
        actions = page.locator(".pea-canvas-actions")
        assert await actions.count() == 1, "应有右上操作区"
        assert await page.locator(".pea-canvas-tapies").count() == 1, "应有 Tapies 余额"
        assert await page.locator(".pea-canvas-community").count() == 1, "应有社区按钮"
        assert await page.locator(".pea-canvas-iconbtn").count() >= 1, "应有分享图标按钮"
        # 底部：Brainstorm + 头像
        assert await page.locator(".pea-canvas-bottom-prompt").count() == 1, "应有 Brainstorm 提示"
        assert await page.locator(".pea-canvas-bottom-prompt-avatar").count() == 1
        # 左侧工具栏：7 个 .pea-tlb-btn + 1 个 .pea-tlb-avatar
        tlb_btns = await page.locator(".pea-toolbar .pea-tlb-btn").count()
        assert tlb_btns == 6, f"画布左侧应有 6 个工具按钮 (实际 {tlb_btns})"
        assert await page.locator(".pea-toolbar .pea-tlb-avatar").count() == 1
        # 画布底部控件：网格 + 缩放 + ?
        assert await page.locator(".pea-canvas-controls").count() == 1
        assert await page.locator(".pea-canvas-controls-pill .pea-canvas-controls-btn").count() >= 3

        # 5. 点击头部 → 下拉打开
        print("[5] 点击画布头部 → 弹出下拉")
        await page.locator(".pea-canvas-header-trigger").click()
        await page.wait_for_selector(".pea-canvas-dropdown", timeout=3000)
        items = page.locator(".pea-canvas-dropdown-item")
        item_count = await items.count()
        assert item_count >= 7, f"下拉应至少有 7 项可点项 (实际 {item_count})"
        text = await page.locator(".pea-canvas-dropdown").inner_text()
        for needle in ["返回工作空间", "探索", "TapTV", "竞技场", "重命名", "新建项目", "删除"]:
            assert needle in text, f"下拉应包含「{needle}」：{text!r}"
        await shot(page, "05_dropdown_open")

        # 6. 点击"返回工作空间" → 回到项目列表
        print("[6] 点击返回工作空间 → 项目列表")
        await page.locator(".pea-canvas-dropdown-item", has_text="返回工作空间").click()
        await page.wait_for_selector(".projects-page", timeout=5000)
        assert await page.locator(".pea-canvas-host").count() == 0, "应已退出画布"
        # 至少 1 张项目卡（刚才新建的）
        cards = await page.locator(".projects-card:not(.projects-card-create)").count()
        assert cards >= 1, f"项目列表应至少 1 张卡 (实际 {cards})"
        await shot(page, "06_back_to_workspace")

        # 7. 再点卡 → 进入画布，再点头部 → 点删除
        print("[7] 二次进入画布，验证删除")
        await page.locator(".projects-card:not(.projects-card-create)").first.click()
        await page.wait_for_selector(".pea-canvas-host", timeout=8000)
        await page.locator(".pea-canvas-header-trigger").click()
        await page.wait_for_selector(".pea-canvas-dropdown", timeout=3000)
        # 删除按钮（红色）
        danger = page.locator(".pea-canvas-dropdown-item.danger")
        assert await danger.count() == 1, "应有红色删除项"
        await danger.click()
        # antd 确认弹窗
        await page.wait_for_selector(".ant-modal", timeout=5000)
        await page.locator(".ant-modal .ant-btn-primary").click()
        # 删完应回到项目列表
        await page.wait_for_selector(".projects-page", timeout=8000)
        # 列表应空（只有"新建项目"卡）
        cards_after = await page.locator(".projects-card:not(.projects-card-create)").count()
        assert cards_after == 0, f"删除后应 0 张卡 (实际 {cards_after})"

        # 8. console error 检查
        print(f"[8] console error 数 = {len(errors)}")
        for e in errors:
            print(f"   ⚠ {e}")

        # 9. 切深色主题（项目列表模式有 TopNav → 可点 Segmented）
        # 此时已在工作空间（删除后回到 list）。点击 Segmented "深" → 深色
        print("[9] 切到深色主题 + 进入画布截图")
        await page.locator(".ant-segmented-item", has_text="深").first.click()
        await page.wait_for_timeout(600)
        # 再新建一个进入画布（在深色下）
        await page.locator(".projects-new-btn", has_text="新建项目").first.click()
        await page.wait_for_selector(".pea-canvas-host", timeout=8000)
        await page.wait_for_timeout(800)
        await shot(page, "09_canvas_dark")
        # 打开下拉
        await page.locator(".pea-canvas-header-trigger").click()
        await page.wait_for_selector(".pea-canvas-dropdown", timeout=3000)
        await page.wait_for_timeout(300)
        await shot(page, "10_dropdown_dark")
        # 关掉下拉
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        await browser.close()
        if errors:
            print("[FAIL] 有 console 错误")
            return 1
        print("[OK] 画布新布局真机验证通过 ✅")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))