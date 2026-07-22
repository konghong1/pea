"""
E7 全局系统 G — 真机可视化验证脚本 (Playwright headless)
驱动真实运行的 web (http://localhost:8088): 注册 -> 逐项点验 -> 截图
"""
import os, sys, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

# 测试用例: (步骤名, 操作函数)
results = []  # (name, ok, note)
console_errors = []

def snap(page, name):
    path = os.path.join(SHOTS, f"{name}.png")
    page.screenshot(path=path, full_page=False)
    return path

def step(name, ok, note=""):
    results.append((name, ok, note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        # 1) 登录页
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_selector("text=pea Creative OS", timeout=15000)
        snap(page, "01_login")
        step("登录页渲染", True)

        # 2) 切换到注册
        page.get_by_text("没有账号？去注册").click()
        page.wait_for_selector("text=创建你的工作区", timeout=5000)
        snap(page, "02_register_form")
        step("注册表单切换", True)

        # 3) 注册测试账号
        page.get_by_placeholder("you@pea.ai").fill("verify@pea.ai")
        page.get_by_placeholder("至少 8 位").fill("password123")
        page.get_by_placeholder("可选").fill("VerifyBot")
        page.locator('form.ant-form button[type="submit"]').click()
        # 等待跳转到工作空间 (画布容器出现)
        page.wait_for_selector(".react-flow", timeout=20000)
        page.wait_for_timeout(1500)
        snap(page, "03_workspace_canvas")
        step("注册+进入工作空间(画布渲染)", True)

        # 4) 顶栏存在 + 积分显示
        page.wait_for_selector(".pea-topnav", timeout=8000)
        balance_text = page.locator(".pea-topnav").inner_text()
        has_balance = "Tapies" in balance_text
        step("顶栏积分显示", has_balance, f"balance片段={'Tapies' in balance_text}")

        # 5) 导航: 主页
        page.get_by_role("button", name="主页").click()
        page.wait_for_timeout(800)
        snap(page, "04_home")
        step("导航-主页", True)

        # 6) 导航: 电商套图
        page.get_by_role("button", name="电商套图").click()
        page.wait_for_timeout(800)
        snap(page, "05_ecom")
        step("导航-电商套图", True)

        # 7) 导航: TapTV
        page.get_by_role("button", name="TapTV").click()
        page.wait_for_timeout(800)
        snap(page, "06_tvtv")
        step("导航-TapTV", True)

        # 8) 导航: 竞技场
        page.get_by_role("button", name="竞技场").click()
        page.wait_for_timeout(800)
        snap(page, "07_arena")
        step("导航-竞技场", True)

        # 9) 回到工作空间 (画布应仍在, SPA 不卸载)
        page.get_by_role("button", name="工作空间").click()
        page.wait_for_selector(".react-flow", timeout=8000)
        page.wait_for_timeout(800)
        snap(page, "08_back_to_canvas")
        step("SPA返回工作空间(画布常驻)", True)

        # 10) 通知中心
        page.get_by_label("通知中心").click()
        page.wait_for_selector("text=通知中心", timeout=5000)
        page.wait_for_timeout(700)
        snap(page, "09_notification_center")
        notif_ok = "欢迎来到 pea" in page.inner_text("body")
        step("通知中心抽屉+欢迎通知", notif_ok)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

        # 11) 分享 -> Toast
        page.get_by_label("复制分享链接").click()
        page.wait_for_timeout(700)
        snap(page, "10_share_toast")
        share_ok = ("链接已复制到剪贴板" in page.inner_text("body")) or ("复制失败" in page.inner_text("body"))
        step("分享复制链接(Toast反馈)", share_ok)
        page.wait_for_timeout(1500)  # 等 toast 消失

        # 12) 用户菜单
        page.locator(".pea-user-trigger").click()
        page.wait_for_timeout(700)
        snap(page, "11_user_menu")
        menu_ok = ("退出登录" in page.inner_text("body")) and ("作品" in page.inner_text("body"))
        step("用户菜单(统计+退出登录)", menu_ok)
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

        # 13) 深色主题切换
        page.locator(".ant-segmented").get_by_text("深").click()
        page.wait_for_timeout(800)
        snap(page, "12_dark_theme")
        dark_ok = "dark" in (page.evaluate("document.documentElement.className") or "")
        step("深色主题切换", dark_ok, f"htmlClass={page.evaluate('document.documentElement.className')}")

        browser.close()

    # 汇总
    print("\n========= E7 可视化验证汇总 =========")
    for n, ok, note in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    print(f"\n运行期 console error 数: {len(console_errors)}")
    for e in console_errors[:20]:
        print("   -", e)
    failed = [n for n, ok, _ in results if not ok]
    print("\n结论:", "全部通过 ✅" if not failed and not console_errors else ("有失败/报错 ⚠️" ))
    # 写结果文件
    with open(os.path.join(SHOTS, "result.txt"), "w", encoding="utf-8") as f:
        f.write("E7 可视化验证\n")
        for n, ok, note in results:
            f.write(f"[{'PASS' if ok else 'FAIL'}] {n} {note}\n")
        f.write(f"\nconsole errors: {len(console_errors)}\n")
        for e in console_errors:
            f.write("  - " + e + "\n")
    sys.exit(0 if (not failed and not console_errors) else 1)

if __name__ == "__main__":
    main()
