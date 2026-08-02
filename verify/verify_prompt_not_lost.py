"""
验证「生成过程中提示词丢失」修复 (Problem 2)
================================================

前置条件:
  - 后端已通过 docker compose 启动 (localhost:8088)。
  - 已安装 py-playwright:  pip install playwright && playwright install chromium

验证点:
  1) 在生成节点的编辑框输入一段特征提示词，点击生成。
  2) 进入生成态后，断言节点上始终显示该提示词 (.pea-node-gen-prompt 含文本)
     —— 对应修复: 生成中覆盖层内回显提示词，杜绝"等待一会儿提示词丢失"的视觉丢失。
  3) 生成过程中多次轮询（模拟"等待一会儿"），提示词应持续可见、不被清空。
  4) 生成中取消选中节点（点击画布空白处）再重新选中，编辑框应恢复出原提示词
     —— 对应修复: 本地草稿/editorText 兜底，必要时回退 data.prompt（无上游时）。

运行:
  python verify_prompt_not_lost.py
"""
import sys, time, os
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
EMAIL = f"e{int(time.time())}@pea.ai"
PW = "password123"
SENTINEL = f"PEA_PROMPT_LOST_TEST_{int(time.time())}"

def log(*a):
    print(*a, flush=True)

def main():
    fails = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: log("PAGEERROR:", str(e)))
        page.on("console", lambda m: log("CONSOLE.ERR:", m.text) if m.type == "error" else None)

        page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector('input[placeholder="you@pea.ai"]', timeout=10000)

        # 注册 / 登录
        try:
            page.fill('input[placeholder="you@pea.ai"]', EMAIL)
            page.fill('input[type="password"]', PW)
            page.click('button:has-text("注册"), button:has-text("创建")')
            page.wait_for_timeout(1500)
        except Exception as e:
            log("登录/注册步骤跳过或失败(可能已登录):", e)

        # 进入画布：等待节点编辑区出现
        page.wait_for_selector(".node-chat-prompt, .pea-node", timeout=15000)

        # 若没有选中节点，尝试新增一个生成节点并选中
        editor = page.locator(".node-chat-prompt [contenteditable], .node-chat-prompt")
        sel_count = page.locator(".pea-node.selected").count()
        if sel_count == 0:
            log("当前无选中节点，尝试添加一个生成节点…")
            add_btn = page.locator('button:has-text("生成"), [data-add-kind="generate"], .pea-add-node')
            if add_btn.count():
                add_btn.first.click()
                page.wait_for_timeout(800)

        # 确保编辑框存在
        if editor.count() == 0:
            fails.append("未找到提示词编辑框 (.node-chat-prompt)")
            return report(fails)

        # 输入特征提示词
        editor.first.click()
        page.keyboard.type(SENTINEL)
        page.wait_for_timeout(400)
        typed = editor.first.inner_text()
        if SENTINEL not in (typed or ""):
            fails.append(f"编辑框未能输入提示词, 实际内容: {(typed or '')[:60]!r}")
            return report(fails)
        log("✓ 已输入特征提示词:", SENTINEL)

        # 点击生成
        gen = page.locator(".pe-launcher")
        if gen.count() == 0:
            fails.append("未找到生成按钮 (.pe-launcher)")
            return report(fails)
        gen.first.click()
        log("✓ 已点击生成，进入生成态…")

        # 等待进入生成态
        try:
            page.wait_for_selector(".pea-node.is-generating, .pea-node-generating", timeout=8000)
            log("✓ 节点已进入生成态")
        except Exception:
            log("⚠ 未检测到生成态标记（可能瞬间完成或选择器差异），继续校验提示词可见性")

        # 校验点 1+3: 生成态下提示词持续可见（轮询 6 次, 每次 5s）
        visible_all = True
        for i in range(6):
            page.wait_for_timeout(5000)
            # 优先在生成覆盖层查找回显提示词
            gen_prompt = page.locator(".pea-node-gen-prompt")
            found = ""
            if gen_prompt.count():
                found = gen_prompt.first.inner_text() or ""
            else:
                # 退化: 节点上的 prompt-echo 文本
                echo = page.locator(".pea-node-prompt-echo-text, .pea-node-generic-prompt")
                if echo.count():
                    found = echo.first.inner_text() or ""
            if SENTINEL not in found:
                visible_all = False
                log(f"  [轮询 {i+1}/6] ✗ 提示词不可见, 采样: {(found or '')[:60]!r}")
            else:
                log(f"  [轮询 {i+1}/6] ✓ 提示词仍可见")
        if not visible_all:
            fails.append("生成过程中提示词在某次轮询中不可见（疑似丢失）")

        # 校验点 4: 取消选中再重新选中，编辑框应恢复提示词
        page.mouse.click(40, 40)  # 点击画布空白处取消选中
        page.wait_for_timeout(600)
        # 重新选中节点
        node = page.locator(".pea-node").first
        if node.count():
            node.click()
            page.wait_for_timeout(800)
        editor2 = page.locator(".node-chat-prompt [contenteditable], .node-chat-prompt")
        if editor2.count():
            restored = editor2.first.inner_text() or ""
            if SENTINEL in restored:
                log("✓ 取消选中后重新选中，编辑框已恢复提示词")
            else:
                fails.append(f"重新选中后编辑框未恢复提示词, 实际: {(restored or '')[:60]!r}")
        else:
            fails.append("重新选中后未找到编辑框")

    report(fails)

def report(fails):
    log("\n========== 验证结果 ==========")
    if not fails:
        log("✅ PASS: 生成过程中提示词未被丢失（可见且可恢复）")
        sys.exit(0)
    else:
        log("❌ FAIL:")
        for f in fails:
            log("  -", f)
        sys.exit(1)

if __name__ == "__main__":
    main()
