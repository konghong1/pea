"""
验证三个修复:
  Q1) AI 提供商列表中文乱码已修复 (不应再出现 æœ¬ / å›¾ 等双编码乱码)
  Q2) 管理员入口可用 (admin@pea.ai 登录后, 用户菜单出现「管理员控制台」并可进入)
  Q3) 浏览器回退回到上一次跳转的页面, 而非退出应用

用法: python verify_three_fixes.py
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
ADMIN_EMAIL = "admin@pea.ai"
ADMIN_PWD = "admin12345"

console_errors = []
results = []


def log_check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def login(page, email, pwd):
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.wait_for_selector("input[placeholder='you@pea.ai']", timeout=15000)
    page.fill("input[placeholder='you@pea.ai']", email)
    page.fill("input[placeholder='至少 8 位']", pwd)
    page.locator("button[type='submit']").click()
    page.wait_for_selector(".pea-topnav", timeout=15000)


def open_user_menu(page):
    page.click(".pea-user-trigger")
    page.wait_for_timeout(400)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        # ---------- Q2: 管理员入口 ----------
        login(page, ADMIN_EMAIL, ADMIN_PWD)
        open_user_menu(page)
        has_admin = page.locator("text=管理员控制台").count() > 0
        log_check("Q2 管理员控制台入口可见", has_admin)
        if has_admin:
            page.locator("text=管理员控制台").first.click()
            page.wait_for_timeout(800)
            admin_visible = page.locator("text=管理员控制台").count() > 0 or page.locator("h2:has-text('管理员控制台')").count() > 0
            # 进入后标题应存在
            title_ok = page.locator("h2").filter(has_text="管理员控制台").count() > 0
            log_check("Q2 点击后进入管理员控制台", title_ok)

        # ---------- Q1: AI 提供商列表乱码 ----------
        # 已在管理员控制台, 默认在「AI 提供商」tab
        page.wait_for_timeout(500)
        prov_text = page.locator(".pea-page").inner_text(timeout=8000)
        has_correct = "Mock 本地占位" in prov_text
        has_mojibake = ("æœ¬" in prov_text) or ("åœ°" in prov_text) or ("Mock æ" in prov_text)
        log_check("Q1 提供商名正确显示", has_correct, '"Mock 本地占位" in table' if has_correct else prov_text[:120])
        log_check("Q1 无双编码乱码", not has_mojibake, ("still has mojibake" if has_mojibake else ""))

        # 模型 & 定价 tab
        page.locator(".ant-tabs-tab:has-text('模型')").click()
        page.wait_for_timeout(600)
        model_text = page.locator(".pea-page").inner_text(timeout=8000)
        model_ok = ("Agnes 图像 2.0 Flash" in model_text) and ("å›¾åƒ" not in model_text)
        log_check("Q1 模型名正确显示", model_ok)

        # 套餐 tab
        page.locator(".ant-tabs-tab:has-text('套餐')").click()
        page.wait_for_timeout(600)
        plan_text = page.locator(".pea-page").inner_text(timeout=8000)
        plan_ok = ("基础套餐" in plan_text) and ("åŸºç¡€" not in plan_text)
        log_check("Q1 套餐名正确显示", plan_ok)

        # ---------- Q3: 浏览器回退 ----------
        # 当前在 admin 控制台(套餐tab). 经 TopNav 回到工作空间.
        page.locator(".pea-nav-item:has-text('工作空间')").click()
        page.wait_for_timeout(600)
        on_workspace = page.locator(".pea-nav-item.active:has-text('工作空间')").count() > 0
        log_check("Q3 前置: 回到工作空间", on_workspace)

        # 工作空间 -> 点导航去「电商套图」
        page.locator(".pea-nav-item:has-text('电商套图')").click()
        page.wait_for_timeout(600)
        on_ecom = page.locator(".pea-nav-item.active:has-text('电商套图')").count() > 0
        log_check("Q3 前置: 跳转到电商套图", on_ecom)

        # 浏览器回退 -> 应回到工作空间 (不退出)
        page.go_back()
        page.wait_for_timeout(800)
        still_in_app = "localhost:8088" in page.url
        back_to_workspace = page.locator(".pea-nav-item.active:has-text('工作空间')").count() > 0
        not_blank = page.evaluate("document.body.innerText.trim().length") > 50
        log_check("Q3 回退后仍停留在应用内", still_in_app and not_blank)
        log_check("Q3 回退回到上一次页面(工作空间)", back_to_workspace)

        # 二级链: 工作空间 -> 账户中心 -> 回退 -> 工作空间
        open_user_menu(page)
        page.locator("text=账户中心").first.click()
        page.wait_for_timeout(600)
        page.go_back()
        page.wait_for_timeout(800)
        back_ws2 = page.locator(".pea-nav-item.active:has-text('工作空间')").count() > 0
        log_check("Q3 二级链: 账户中心回退到工作空间", back_ws2)

        # ---------- console 错误汇总 ----------
        log_check("无 console error", len(console_errors) == 0, "; ".join(console_errors[:5]))

        browser.close()

    print("\n==== 汇总 ====")
    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n总计 {len(results)} 项, 失败 {len(failed)} 项")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
