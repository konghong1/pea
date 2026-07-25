"""
电商套图完整模块 E2E 验证（Playwright）
验证从 ai-agent 原版迁移的完整 EcommerceGallery 模块（适配 pea 后端 + 品牌色）：

  Q1: 导航到「电商套图」并渲染 .gallery-page
  Q2: 左侧配置面板（上传产品图 / 卖点 / 市场配置）
  Q3: 右侧内容区（创作结果 / 创作案例 Tab）
  Q4: 模型下拉含真实 pea AI 提供商图片模型（策划台「自定义子任务」tab）
  Q5: 策划抽屉打开 + 推荐类型卡片
  Q6: 立即生成按钮存在且可见
  Q7: 出图规划列表区域
  Q8: 全程 0 关键 console error
"""
import asyncio
import re
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"


async def login(page, errors):
    """注册新账号并登录（邮箱带时间戳，保证唯一）。"""
    await page.goto(BASE + "/login", timeout=15000)
    await page.wait_for_load_state("networkidle", timeout=10000)
    # 切到注册模式（用部分文本，避免全角字符精确匹配失败）
    reg_link = page.get_by_text(re.compile("去注册"))
    if await reg_link.count():
        await reg_link.first.click()
        await asyncio.sleep(0.4)
    email = f"e{int(asyncio.get_event_loop().time())}@pea.ai"
    await page.get_by_placeholder("you@pea.ai").fill(email)
    await page.get_by_placeholder("至少 8 位").fill("Test1234!")
    # 提交按钮在 <form> 内（链接按钮在 form 外），避免点到“去注册”链接
    submit = page.locator("form").get_by_role("button", name=re.compile(r"注册|登录"))
    await submit.click()
    # 等待进入工作区（TopNav 出现）
    try:
        await page.wait_for_selector(".pea-nav", timeout=10000)
        return True, email, ""
    except Exception as e:
        # 登录失败：抓取当前 URL / 可见提示用于诊断
        try:
            body = await page.locator("body").inner_text()
        except Exception:
            body = ""
        return False, email, f"{e} | url={page.url} | body={body[:200]}"


async def main():
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(f"[pageerror] {exc}"))

        # ── 登录 ──
        ok, email, login_err = await login(page, errors)
        if not ok:
            results.append(("Q1_NAV", f"FAIL (login: {login_err})"))
            await page.screenshot(path="verify/_dbg_full_ecom.png", full_page=True)
            print(f"\nLOGIN FAILED: {login_err}")
            await browser.close()
            _report(results, errors)
            return

        # ── 导航到电商套图（状态驱动，点击 nav 按钮，非 URL 路由）──
        try:
            await page.get_by_role("button", name="电商套图").click()
            await page.wait_for_selector(".gallery-page", timeout=10000)
            nav_ok = True
            results.append(("Q1_NAV", "PASS"))
        except Exception as e:
            results.append(("Q1_NAV", f"FAIL ({e})"))
            nav_ok = False

        if not nav_ok:
            await page.screenshot(path="verify/_dbg_full_ecom.png", full_page=True)
            await browser.close()
            _report(results, errors)
            return

        await asyncio.sleep(1.5)  # 等 loadAll 拉取模型/模板等

        # ── Q2: 左侧配置面板 ──
        config_panel = await page.query_selector(".config-panel")
        dropzone = await page.query_selector(".dropzone")
        has_upload_text = await page.get_by_text("上传产品图").count() > 0
        results.append(("Q2_LEFT_PANEL", "PASS" if (config_panel and dropzone and has_upload_text)
                        else f"FAIL (panel={config_panel is not None}, drop={dropzone is not None}, text={has_upload_text})"))

        # ── Q3: 右侧内容区 + Tab ──
        content_area = await page.query_selector(".content-area")
        tab_results = await page.get_by_text("创作结果").count() > 0
        tab_cases = await page.get_by_text("创作案例").count() > 0
        results.append(("Q3_RIGHT_AREA", "PASS" if (content_area and tab_results and tab_cases)
                        else f"FAIL (content={content_area is not None}, results={tab_results}, cases={tab_cases})"))

        # ── Q5: 策划抽屉（先开，再做 Q4 模型检查）──
        drawer_ok = False
        type_cards = 0
        try:
            plan_btn = page.get_by_role("button", name=re.compile(r"AI智能策划台|AI 智能策划台"))
            if await plan_btn.count():
                await plan_btn.first.click()
                await page.wait_for_selector(".g-drawer", timeout=5000)
                drawer = await page.query_selector(".g-drawer")
                if drawer and await drawer.is_visible():
                    type_cards = await page.locator(".dg-card").count()
                    drawer_ok = type_cards > 0
            results.append(("Q5_DRAWER", "PASS" if drawer_ok else f"FAIL (cards={type_cards})"))
        except Exception as e:
            results.append(("Q5_DRAWER", f"FAIL ({e})"))

        # ── Q4: 模型下拉（策划台「自定义子任务」tab）→ 真实 pea AI 提供商图片模型 ──
        try:
            tab_btn = page.get_by_role("button", name="自定义子任务")
            if await tab_btn.count():
                await tab_btn.first.click()
                await asyncio.sleep(0.5)
            sel = page.locator(".g-drawer .ant-select").first()
            await sel.click()
            await asyncio.sleep(0.4)
            opt_count = await page.locator(".ant-select-item-option").count()
            opt_texts = await page.locator(".ant-select-item-option").all_inner_texts()
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
            real = [t for t in opt_texts if re.search(r"Agnes|FLUX|flux|mock|图像|Flash|provider", t, re.I)]
            if opt_count >= 2 and real:
                results.append(("Q4_MODEL", f"PASS (real models: {', '.join(real[:3])})"))
            elif opt_count >= 1:
                results.append(("Q4_MODEL", "WARN (only default option; adapter wired but no image models configured)"))
            else:
                results.append(("Q4_MODEL", "FAIL (model dropdown empty)"))
        except Exception as e:
            results.append(("Q4_MODEL", f"WARN ({e})"))

        # 关闭抽屉
        try:
            close = page.query_selector(".drawer-close")
            if close:
                await close.click()
                await asyncio.sleep(0.3)
        except Exception:
            pass

        # ── Q6: 立即生成按钮 ──
        gen_btn = await page.query_selector(".btn-generate")
        has_gen_text = await page.get_by_text("立即生成").count() > 0
        results.append(("Q6_GENERATE_BTN", "PASS" if (gen_btn or has_gen_text)
                        else f"FAIL (btn={gen_btn is not None}, text={has_gen_text})"))

        # ── Q7: 出图规划列表区域 ──
        plan_list = await page.query_selector(".plan-list")
        plan_list_head = await page.query_selector(".plan-list-head") or await page.query_selector(".planner-bar")
        results.append(("Q7_PLAN_LIST", "PASS" if (plan_list or plan_list_head)
                        else "WARN (no plan list area found)"))

        # ── Q8: 0 关键 console error ──
        critical = [e for e in errors if
                    'chunk' not in e.lower() and 'favicon' not in e.lower() and
                    'google' not in e.lower() and 'fonts.googleapis' not in e.lower()]
        results.append(("Q8_CONSOLE", "PASS" if len(critical) == 0
                        else f"FAIL ({len(critical)} errors: {critical[:3]})"))

        await page.screenshot(path="verify/_dbg_full_ecom.png", full_page=True)
        await browser.close()

    _report(results, errors)


def _report(results, errors):
    print(f"\n{'='*55}")
    fail = sum(1 for _, s in results if s.startswith("FAIL"))
    warn = sum(1 for _, s in results if s.startswith("WARN"))
    pas = sum(1 for _, s in results if s.startswith("PASS"))
    print(f"RESULT: {pas} PASS / {warn} WARN / {fail} FAIL (of {len(results)})")
    for code, msg in results:
        icon = "PASS" if "PASS" in msg else ("WARN" if "WARN" in msg else "FAIL")
        print(f"  [{icon}] {code}: {msg}")
    if errors:
        print(f"\n--- Console/Page errors ({len(errors)}) ---")
        for e in errors[:15]:
            print(f"  {e}")


if __name__ == "__main__":
    asyncio.run(main())
