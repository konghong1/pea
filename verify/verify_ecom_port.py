"""验证电商套图模块已移植到 pea 并适配 AI 提供商模型选择 (打 :8088)。
检查项：
  Q1 页面渲染（hero + 4 步骤区）
  Q2 模型下拉含 pea 真实模型（/models/available），可选中
  Q3 添加出图规划（抽屉保存）
  Q4 一键生成触发任务并提交到 pea 生成后端（结果卡片出现）
  Q5 0 console error / 不白屏
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
PASSED = 0
FAILED = 0

def log(label, ok, extra=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [PASS] {label}{(' — ' + extra) if extra else ''}")
    else:
        FAILED += 1
        print(f"  [FAIL] {label}{(' — ' + extra) if extra else ''}")

def login(page, email, pwd):
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.wait_for_timeout(900)
    page.fill('input[placeholder*="邮箱"], input[id="email"]', email)
    page.fill('input[placeholder*="密码"], input[type="password"]', pwd)
    page.keyboard.press("Enter")
    page.wait_for_selector(".pea-topnav", timeout=15000)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    page.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append(f"PAGEERROR: {e}"))

    print("=== 登录 admin ===")
    login(page, "admin@pea.ai", "admin12345")
    page.wait_for_timeout(1500)

    print("=== 进入电商套图 ===")
    page.locator(".pea-nav-item", has_text="电商套图").click()
    page.wait_for_timeout(1200)

    # Q1 页面渲染
    hero = page.locator(".pea-hero-title", has_text="电商套图")
    log("Q1 hero 标题渲染", hero.count() > 0)
    sections = page.locator(".ecom-section")
    log("Q1 四个步骤区渲染", sections.count() >= 4, f"{sections.count()} 区")
    not_blank = page.evaluate("document.body.innerText.trim().length") > 100
    log("Q1 页面非空（非白屏）", not_blank)

    # Q2 模型下拉含真实模型
    print("=== Q2 模型选择（pea /models/available）===")
    sel = page.locator(".ecom-model-select")
    log("Q2 模型下拉存在", sel.count() > 0)
    sel.click()
    page.wait_for_timeout(800)
    opts = page.locator(".ant-select-dropdown:visible .ant-select-item-option")
    opt_texts = opts.all_inner_texts()
    joined = " | ".join(opt_texts)
    log("Q2 下拉出现模型选项", opts.count() > 0, f"{opts.count()} 项")
    has_ag = any("Agnes" in t for t in opt_texts)
    log("Q2 含 pea 真实模型（Agnes）", has_ag, joined[:80])
    # 选中第一个可用模型
    if opts.count() > 0:
        opts.first.click()
        page.wait_for_timeout(500)
    val = page.locator(".ecom-model-select .ant-select-selection-item")
    log("Q2 模型已选中", val.count() > 0, val.first.inner_text() if val.count() else "")

    # Q3 添加出图规划
    print("=== Q3 添加出图规划 ===")
    page.locator(".ecom-type-card").first.click()  # 主图
    page.wait_for_selector(".ant-drawer", timeout=8000)
    page.wait_for_timeout(900)
    drawer = page.locator(".ant-drawer")
    log("Q3 策划抽屉打开", drawer.count() > 0)
    # antd 给两字中文按钮插入空格，实际文本为「保 存」；按 footer 第 2 个按钮点击更稳
    save_btn = page.locator(".ant-drawer .ecom-drawer-footer button").nth(1)
    log("Q3 保存按钮可见", save_btn.count() > 0)
    save_btn.click(force=True)
    page.wait_for_timeout(800)
    plan_items = page.locator(".ecom-plan-item")
    log("Q3 规划已加入列表", plan_items.count() > 0, f"{plan_items.count()} 条")

    # Q4 一键生成
    print("=== Q4 一键生成（pea 生成后端）===")
    gen_btn = page.locator("button.ant-btn-primary", has_text="生成")
    log("Q4 生成按钮存在", gen_btn.count() > 0)
    gen_btn.first.click()
    page.wait_for_timeout(2500)  # 等待任务提交 + 轮询
    results = page.locator(".ecom-result-card")
    log("Q4 生成结果卡片出现（任务已提交）", results.count() > 0, f"{results.count()} 张")

    # Q5 console error
    log("Q5 无 console error", len(errs) == 0)
    if errs:
        for e in errs[:8]:
            print(f"    ERR: {e}")

    print(f"\n{'='*48}\n结果: {PASSED} 通过 / {FAILED} 失败 (共 {PASSED+FAILED})")
    browser.close()

sys.exit(0 if FAILED == 0 else 1)
