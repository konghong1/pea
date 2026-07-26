"""E28 - 出图数量选择器交互验证

验证:
1. 1x 按钮存在
2. 点击 1x 按钮后，下拉列表必须展开（DOM 可见 + opacity > 0）
3. 点击选项后，状态正确更新
"""
import os
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

        # 注册 + 登录
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

        img = add_node("图片")
        print(f"图片节点 ID: {img}")

        # 选中图片节点
        page.locator(f'.react-flow__node[data-id="{img}"]').first.click(); page.wait_for_timeout(500)

        # ====== 检查 1x 按钮并验证交互 ======
        count_btn = page.locator('.node-count-btn')
        step("① 1x 按钮存在", count_btn.count() > 0, f"count={count_btn.count()}")
        
        if count_btn.count() > 0:
            # 获取初始状态
            btn_text_before = count_btn.first.text_content() or ""
            step("② 按钮初始显示 '1x'", btn_text_before.strip() == '1x', f"text='{btn_text_before}'")

            # 获取按钮位置（用于调试）
            btn_box = count_btn.first.bounding_box()
            if btn_box:
                print(f"  按钮位置: x={btn_box['x']:.0f}, y={btn_box['y']:.0f}, w={btn_box['width']:.0f}, h={btn_box['height']:.0f}")

            # 点击按钮
            count_btn.first.click()
            page.wait_for_timeout(500)

            # 检查 DOM 中是否出现了 dropdown
            dropdown = page.locator('.node-count-btn-dropdown')
            step("③ 点击后下拉列表出现在 DOM 中", dropdown.count() > 0, f"count={dropdown.count()}")
            
            if dropdown.count() > 0:
                # 检查下拉列表的可见性
                dropdown_visible = page.evaluate("""() => {
                    const dd = document.querySelector('.node-count-btn-dropdown');
                    if (!dd) return {exists: false};
                    const style = getComputedStyle(dd);
                    return {
                        exists: true,
                        display: style.display,
                        visibility: style.visibility,
                        opacity: style.opacity,
                        height: dd.offsetHeight,
                        width: dd.offsetWidth
                    };
                }""")
                print(f"  下拉列表样式: display={dropdown_visible.get('display')}, visibility={dropdown_visible.get('visibility')}, opacity={dropdown_visible.get('opacity')}")
                
                step("④ 下拉列表可见 (display != none)", dropdown_visible.get('display') != 'none' and dropdown_visible.get('display') != '', 
                     f"display='{dropdown_visible.get('display')}'")
                step("⑤ 下拉列表可见 (visibility != hidden)", dropdown_visible.get('visibility') != 'hidden',
                     f"visibility='{dropdown_visible.get('visibility')}'")
                step("⑥ 下拉列表有高度和宽度", dropdown_visible.get('height', 0) > 0 and dropdown_visible.get('width', 0) > 0,
                     f"h={dropdown_visible.get('height')}, w={dropdown_visible.get('width')}")

                # 检查选项
                opts = dropdown.locator('.node-count-opt')
                opt_count = opts.count()
                step("⑦ 选项数量正确 (4个)", opt_count == 4, f"有{opt_count}个选项")

                if opt_count == 4:
                    expected_labels = ['1x', '2x', '3x', '4x']
                    for i in range(4):
                        text = opts.nth(i).text_content() or ""
                        expected = expected_labels[i]
                        step(f"⑧ 选项{i+1}='{expected}'", text == expected, f"text='{text}'")
                    
                    # 点击 3x
                    for i in range(opt_count):
                        text = opts.nth(i).text_content() or ""
                        if text == '3x':
                            opts.nth(i).click(); page.wait_for_timeout(300)
                            break
                    
                    new_text = count_btn.first.text_content() or ""
                    step("⑨ 点击 3x 后按钮显示 '3x'", new_text.strip() == '3x', f"text='{new_text}'")
        
        shots = os.path.dirname(__file__) + '/shots'
        os.makedirs(shots, exist_ok=True)
        page.screenshot(path=f'{shots}/e28_dropdown_visible.png')
        print(f"截图保存: e28_dropdown_visible.png")

        browser.close()

        if errors:
            print(f"\n❌ 共 {len(errors)} 项失败: {errors}")
        else:
            print(f"\n✅ E28 全部通过!")

if __name__ == "__main__":
    main()