"""E28 - 出图数量选择器最终验证

验证流程:
1. 注册 + 创建项目 + 添加图片节点
2. 选中节点 → 输入栏出现 → 检查 1x 按钮是否存在且可点击
3. 点击 1x → 下拉列表展开 → 检查 1x/2x/3x/4x 选项都可见
4. 点击 3x → 验证按钮文本变为 "3x"
5. 再次点击 3x 按钮 → 验证下拉重新展开且 3x 高亮
"""
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

        # ====== 测试 1: 1x 按钮存在且显示正确 ======
        count_btn = page.locator('.node-count-btn')
        step("① 1x 按钮存在", count_btn.count() > 0, f"count={count_btn.count()}")
        if count_btn.count() > 0:
            btn_text = count_btn.first.text_content() or ""
            step("② 1x 按钮默认显示 '1x'", btn_text.strip() == '1x', f"text='{btn_text}'")

            # ====== 测试 2: 点击展开下拉列表 ======
            count_btn.first.click(); page.wait_for_timeout(300)

            dropdown = page.locator('.node-count-btn-dropdown')
            step("③ 下拉列表已展开", dropdown.count() > 0, f"count={dropdown.count()}")
            
            if dropdown.count() > 0:
                opts = dropdown.locator('.node-count-opt')
                opt_count = opts.count()
                step("④ 选项数量正确 (4个)", opt_count == 4, f"有{opt_count}个选项")

                if opt_count == 4:
                    # 检查每个选项的文本
                    for i in range(4):
                        text = opts.nth(i).text_content() or ""
                        expected = [f"{i+1}x"][0]
                        step(f"⑤ 选项{i+1}='{expected}'", text == expected, f"text='{text}'")

                    # 检查 1x 初始高亮
                    first_active = opts.first.get_attribute('class') or ''
                    step("⑥ 1x 初始高亮 (active class)", 'active' in first_active, f"class='{first_active}'")

                    # ====== 测试 3: 点击 3x ======
                    # 找到 3x 选项并点击（跳过索引，按文本）
                    for i in range(opt_count):
                        text = opts.nth(i).text_content() or ""
                        if text == '3x':
                            opts.nth(i).click(); page.wait_for_timeout(300)
                            break

                    new_text = count_btn.first.text_content() or ""
                    step("⑦ 点击 3x 后按钮显示 '3x'", new_text.strip() == '3x', f"text='{new_text}'")

                    # ====== 测试 4: 关闭后再展开，3x 仍高亮 ======
                    count_btn.first.click(); page.wait_for_timeout(300)
                    
                    dropdown2 = page.locator('.node-count-btn-dropdown')
                    step("⑧ 关闭后重新展开", dropdown2.count() > 0, f"count={dropdown2.count()}")
                    
                    if dropdown2.count() > 0:
                        active_opt = dropdown2.locator('.node-count-opt.active')
                        active_text = active_opt.first.text_content() if active_opt.count() > 0 else ""
                        step("⑨ 重新展开后 3x 仍然高亮", active_opt.count() > 0 and '3x' in active_text, f"active_text='{active_text}'")
        
        # 截图
        shots = os.path.dirname(__file__) + '/shots'
        os.makedirs(shots, exist_ok=True)
        page.screenshot(path=f'{shots}/e28_final.png')
        print(f"截图保存: e28_final.png")

        browser.close()

        if errors:
            print(f"\n❌ 共 {len(errors)} 项失败: {errors}")
        else:
            print(f"\n✅ E28 全部通过!")

if __name__ == "__main__":
    main()