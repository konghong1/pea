from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(600)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    ts = int(time.time())
    page.fill('input[placeholder="you@pea.ai"]', f"diag3_{ts}@pea.dev")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "D")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)

    # 点击新建项目
    page.get_by_role("button", name="新建项目").first.click()
    page.wait_for_timeout(1500)
    page.screenshot(path="C:/workspace/pea/verify/shots/diag_newproj.png")
    print("URL after new project click:", page.url)
    print("has viewport:", page.locator(".react-flow__viewport").count())
    # 检查是否有模态框
    modal = page.locator(".ant-modal, [role=dialog]").first
    print("modal count:", page.locator(".ant-modal, [role=dialog]").count())
    if modal.count():
        print("modal text:", modal.inner_text()[:300])
        # 列出模态框内输入框
        inputs = modal.locator("input").all()
        for i in inputs:
            print("  input placeholder:", i.get_attribute("placeholder"))
    # 列出当前可见输入框（任意）
    inputs_all = page.locator("input").all_inner_texts()
    print("all inputs:", [x for x in inputs_all if x.strip()][:10])
    b.close()
