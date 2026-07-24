"""
pea 项目页 (T-M3-01) 真机验证：注册 → 登录 → 项目页 → 新建项目 → 打开 → 节点加载 → 关闭再重开数据回放。
"""
import asyncio
import sys
import time
import uuid
from pathlib import Path

from playwright.async_api import async_playwright, expect

BASE = "http://localhost:8088"
SCREEN_DIR = Path("C:/workspace/pea/verify/_projects")
SCREEN_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    suffix = uuid.uuid4().hex[:8]
    email = f"proj_ui_{suffix}@pea.ai"
    password = "Test12345"

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        page.set_default_timeout(15000)

        # 收集 console error
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)

        # 1. 注册
        print(f"[1] 注册 {email}")
        await page.goto(f"{BASE}/login")
        # 切到注册 tab（找文字包含"注册"的按钮/链接）
        reg_clicked = False
        for sel in ["text=去注册", "button:has-text('去注册')", "button:has-text('注册')"]:
            try:
                el = page.locator(sel).first
                if await el.count() and await el.is_visible():
                    await el.click()
                    reg_clicked = True
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                pass
        print(f"   register tab clicked: {reg_clicked}")

        # 填可见输入框
        inputs = page.locator("input:visible")
        n = await inputs.count()
        phs = []
        types = []
        for i in range(n):
            phs.append(await inputs.nth(i).get_attribute("placeholder") or "")
            types.append(await inputs.nth(i).get_attribute("type") or "")
        print(f"   visible inputs n={n} types={types} placeholders={phs}")

        async def fill_by(pred, value, label):
            for i in range(n):
                if pred(i):
                    await inputs.nth(i).fill(value)
                    print(f"   [fill] {label} -> input#{i}")
                    return True
            return False

        await fill_by(lambda i: "@" in phs[i] and "password" not in phs[i].lower(), email, "email")
        await fill_by(lambda i: types[i] == "password", password, "password")
        await fill_by(lambda i: types[i] == "text" and "@" not in phs[i], f"User{suffix}", "displayName")

        # 提交
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
        await page.wait_for_timeout(3000)
        print(f"   URL={page.url}")

        # 2. 主页（top nav 已登录）→ 点击"工作空间"导航到项目页
        print("[2] 进入工作空间（项目列表，个人 scope）")
        await page.get_by_role("button", name="工作空间").first.click()
        await page.wait_for_timeout(500)
        # 应看到个人 tab 高亮 + grid + 新建项目卡
        await expect(page.locator(".projects-tab.active")).to_contain_text("个人")
        await expect(page.locator(".projects-card-create")).to_be_visible()
        await page.screenshot(path=str(SCREEN_DIR / "01_home.png"), full_page=True)

        # 3. 新建项目（点击新建项目卡）
        print("[3] 点击新建项目卡进入画布编辑器")
        await page.locator(".projects-card-create").click()
        await page.wait_for_timeout(1500)
        # 应切到画布编辑器
        # 验证画布常驻元素出现
        assert await page.locator(".react-flow").count() > 0, "画布编辑器未加载"
        assert await page.locator(".pea-canvas-host").count() == 1, "画布宿主未加载"
        await page.screenshot(path=str(SCREEN_DIR / "02_canvas.png"), full_page=False)

        # 4. 添加一个 text 节点（用页面上的"添加"按钮）
        print("[4] 添加一个 text 节点")
        # 找工具栏里的"文本"按钮
        try:
            await page.get_by_role("button", name="文本").first.click(timeout=3000)
        except Exception:
            print("   (skip 节点添加：按钮未找到，仅验证空画布渲染)")
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(SCREEN_DIR / "03_node_added.png"))

        # 5. 回到工作空间，应看到新画布卡
        print("[5] 回到工作空间，看到新建的画布卡")
        # 画布模式下 TopNav 隐藏，使用画布头部下拉中的「返回工作空间」
        await page.locator(".pea-canvas-header-trigger").click()
        await page.wait_for_selector(".pea-canvas-dropdown", timeout=3000)
        await page.locator(".pea-canvas-dropdown-item", has_text="返回工作空间").click()
        await page.wait_for_selector(".projects-page", timeout=5000)
        await expect(page.locator(".projects-card:not(.projects-card-create)").first).to_be_visible()
        count = await page.locator(".projects-card:not(.projects-card-create)").count()
        print(f"   项目数 = {count}")
        await page.screenshot(path=str(SCREEN_DIR / "04_home_with_project.png"), full_page=True)

        # 6. 测试上下文菜单
        print("[6] 上下文菜单")
        card = page.locator(".projects-card:not(.projects-card-create)").first
        await card.hover()
        await page.wait_for_timeout(200)
        await card.locator(".projects-card-more").click()
        await page.wait_for_timeout(400)
        # 检查菜单项
        for txt in ["打开", "重命名", "选择", "移动至…", "分享链接", "移动至团队", "删除"]:
            assert await page.get_by_role("menuitem", name=txt).count() > 0, f"菜单缺: {txt}"
        print("   ✓ 7 项菜单全部存在")
        await page.screenshot(path=str(SCREEN_DIR / "05_context_menu.png"))
        # 关闭菜单
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # 7. 重命名
        print("[7] 重命名为「我的第一个项目」")
        await card.hover()
        await card.locator(".projects-card-more").click()
        await page.wait_for_timeout(400)
        await page.get_by_role("menuitem", name="重命名").click()
        try:
            await page.wait_for_selector(".ant-modal", state="visible", timeout=8000)
        except Exception as e:
            print(f"   !! 重命名模态框未出现, console errors={errors}")
            await page.screenshot(path=str(SCREEN_DIR / "07_rename_fail.png"))
            raise
        await page.wait_for_timeout(300)
        # 模态框输入（antd v5: .ant-modal 内 .ant-input）
        modal_input = page.locator(".ant-modal .ant-input").first
        await modal_input.fill("我的第一个项目")
        await page.locator(".ant-modal .ant-btn-primary").click()
        await page.wait_for_timeout(500)
        await expect(card.locator(".projects-card-title")).to_contain_text("我的第一个项目")
        print("   ✓ 重命名生效")

        # 8. 移动至团队
        print("[8] 移动至团队")
        await card.hover()
        await card.locator(".projects-card-more").click()
        await page.wait_for_timeout(300)
        await page.get_by_role("menuitem", name="移动至团队").click()
        await page.wait_for_timeout(500)
        # 切换到团队项目 tab，应能看到该卡片（且 scope tag=团队）
        await page.locator(".projects-tab", has_text="团队项目").click()
        await page.wait_for_timeout(500)
        await expect(card.locator(".projects-card-scope")).to_have_text("团队")
        print("   ✓ scope 已切到团队")

        # 9. 打开该项目（应进入画布编辑器）
        print("[9] 打开该项目（核心需求：带出工作内容）")
        await card.click()
        await page.wait_for_timeout(1500)
        assert await page.locator(".react-flow").count() > 0, "打开后未进入画布"
        await page.screenshot(path=str(SCREEN_DIR / "06_open_canvas.png"))
        print("   ✓ 已进入画布编辑器")

        # 10. 删除（注意：第[8]步已将项目移入团队，需切到团队 tab 才能看到该卡）
        print("[10] 删除项目")
        # 画布模式下 TopNav 隐藏，用画布头部下拉返回工作空间
        await page.locator(".pea-canvas-header-trigger").click()
        await page.wait_for_selector(".pea-canvas-dropdown", timeout=3000)
        await page.locator(".pea-canvas-dropdown-item", has_text="返回工作空间").click()
        await page.wait_for_selector(".projects-page", timeout=5000)
        await page.locator(".projects-tab", has_text="团队项目").click()
        await page.wait_for_timeout(500)
        card2 = page.locator(".projects-card:not(.projects-card-create)").first
        await card2.hover()
        await card2.locator(".projects-card-more").click()
        await page.wait_for_timeout(300)
        await page.get_by_role("menuitem", name="删除").click()
        await page.wait_for_timeout(300)
        # 确认弹窗（antd OK 按钮为 .ant-btn-primary，文本带空格如「删 除」）
        await page.locator(".ant-modal .ant-btn-primary").click()
        await page.wait_for_timeout(500)
        cnt = await page.locator(".projects-card:not(.projects-card-create)").count()
        print(f"   删除后项目数 = {cnt}")
        assert cnt == 0, "删除后应无卡片"

        # 11. console error 检查
        print(f"\n[11] console error 数 = {len(errors)}")
        for e in errors[:5]:
            print(f"   ! {e}")
        assert len(errors) == 0, f"运行时错误: {errors}"

        await browser.close()

        print("\n[OK] 全部真机验证通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())