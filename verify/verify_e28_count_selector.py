"""E28 - 出图数量功能验证

验证:
1. 图片节点选中后，输入栏右侧显示 1x/2x/3x/4x 按钮
2. 点击按钮弹出下拉选择器，包含完整选项
3. 选择不同数量后按钮文本正确更新
"""
from __future__ import annotations
import os, time
from playwright.sync_api import sync_playwright

WEB = "http://localhost:8088"

def main():
    errors = []
    def step(label, ok, detail=""):
        icon = "PASS" if ok else "FAIL"
        print(f"[{icon}] {label}  {detail}")
        if not ok: errors.append(label)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"console:{m.type}:{m.text[:120]}") if m.type == "error" else None)

        # 注册 + 登录到 workspace
        page.goto(WEB, wait_until="networkidle")
        ts = page.evaluate("Date.now()")
        email = f"e28_{ts}@pea.ai"
        if page.locator("text=去注册").count() > 0:
            page.locator("text=去注册").first.click(); page.wait_for_timeout(500)
        ins = page.locator("input:visible"); cnt = ins.count()
        if cnt >= 2:
            ins.nth(0).fill(email); page.wait_for_timeout(120)
            ins.nth(1).fill("test1234"); page.wait_for_timeout(120)
            if cnt >= 3: ins.nth(2).fill("E28")
        page.locator("button", has_text="注").first.click(); page.wait_for_timeout(1500)
        page.wait_for_selector("text=新建项目", timeout=8000)
        page.locator("text=新建项目").first.click(); page.wait_for_timeout(900)
        page.wait_for_selector(".react-flow", timeout=10000); page.wait_for_timeout(400)

        def add_node(label):
            page.locator(".pea-tlb-btn[aria-label*='添加节点']").first.click(); page.wait_for_timeout(250)
            page.locator(f".pea-add-menu-item:has-text('{label}')").first.click(); page.wait_for_timeout(350)
            return page.evaluate("""() => { const s=window.__canvas.getState(); const ns=s.nodes; return ns[ns.length-1].id; }""")

        # 添加图片节点
        img = add_node("图片")
        print(f"图片节点 ID: {img}")

        # 选中图片节点
        page.locator(f'.react-flow__node[data-id="{img}"]').first.click(); page.wait_for_timeout(500)

        # 检查出图数量选择器
        count_btn = page.locator('.node-count-btn')
        step("出图数量选择器已显示", count_btn.count() > 0, f"count={count_btn.count()}")
        if count_btn.count() > 0:
            btn_text = count_btn.first.text_content() or ""
            step("按钮默认显示 1x", "1" in btn_text, f"text='{btn_text}'")

            # 点击展开
            count_btn.first.click(); page.wait_for_timeout(300)

            # 检查下拉列表
            dropdown = page.locator('.node-count-btn-dropdown')
            step("下拉列表已展开", dropdown.count() > 0, f"count={dropdown.count()}")
            if dropdown.count() > 0:
                opts = dropdown.locator('.node-count-opt')
                count_opts = opts.count()
                step("选项数量正确", count_opts == 4, f"有{count_opts}个选项")

                # 收集所有选项文本
                opt_texts = []
                for i in range(count_opts):
                    text = opts.nth(i).text_content() or ""
                    opt_texts.append(text)
                    step(f"选项{i+1} 存在", any(c in text for c in ['1x', '2x', '3x', '4x']), f"text='{text}'")

                # 选择 3x
                opts_3x = dropdown.locator(':text("3x"), :text("3 张")')
                if opts_3x.count() > 0:
                    # 先截图查看下拉列表状态
                    page.screenshot(path=f'{os.path.dirname(__file__)}/shots/e28_dropdown_before_click.png')
                    
                    opts_3x.first.click(); page.wait_for_timeout(500)
                    
                    # 点击后 dropdown 应该消失，但 count_btn 应该显示 3x
                    new_text = count_btn.first.text_content() or ""
                    step("选择 3x 后按钮显示 3x", "3" in new_text and "x" in new_text, f"text='{new_text}'")

                    # 验证：重新展开下拉列表，检查 active 类
                    count_btn.first.click(); page.wait_for_timeout(300)
                    dropdown2 = page.locator('.node-count-btn-dropdown')
                    if dropdown2.count() > 0:
                        active_opt = dropdown2.locator('.node-count-opt.active')
                        active_text = active_opt.first.text_content() if active_opt.count() > 0 else ""
                        step("重新展开后 3x 高亮", active_opt.count() > 0 and "3x" in active_text, f"active_text='{active_text}'")
                        page.screenshot(path=f'{os.path.dirname(__file__)}/shots/e28_dropdown_active.png')
                    else:
                        step("重新展开下拉列表", False, "dropdown 未出现")
                else:
                    step("找到 3x 选项", False, "未找到 :text('3x')")

        # 截图验证
        page.screenshot(path=f'{os.path.dirname(__file__)}/shots/e28_count_selector.png')
        print("截图保存: e28_count_selector.png")

        # 关闭浏览器
        browser.close()

        if errors:
            print(f"\n[FAIL] 共 {len(errors)} 项失败: {errors}")
        else:
            print("\n[PASS] E28 测试全部通过!")

if __name__ == "__main__":
    main()