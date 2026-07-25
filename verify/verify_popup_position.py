"""验证弹出层定位：点击模型选择/比例选择按钮后，弹出层应出现在按钮上方（抽拉式）"""
import time
from playwright.sync_api import sync_playwright

def main():
    errors = []
    logs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text[:150]) if m.type == "error" else logs.append(m.text) if m.text.startswith('[usePopupPosition]') else None)

        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(800)
        
        # 注册（复用 verify_pan_add.py 的逻辑）
        ts = int(time.time() * 1000)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', f"pop_{ts}@pea.ai")
        page.fill('input[type="password"]', "Test1234!")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(5000)

        # 进画布
        page.wait_for_selector("text=新建项目", timeout=10000)
        page.click("text=新建项目")
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(1500)

        # 通过工具栏添加图片节点（复用 verify_pan_add.py 的方式）
        page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
        page.wait_for_selector(".pea-add-menu", timeout=4000)
        for it in page.locator(".pea-add-menu-item").all():
            if "图片" in (it.text_content() or ""):
                box = it.bounding_box()
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.wait_for_timeout(2000)
                break
        
        # 确认添加成功
        node_count = page.locator(".react-flow__node").count()
        print(f"当前节点数: {node_count}")
        if node_count == 0:
            print("❌ 节点添加失败，跳过测试")
            browser.close()
            return

        # 点击节点
        node = page.locator(".react-flow__node").first
        node.click()
        page.wait_for_timeout(1000)

        # 截图保存当前状态
        page.screenshot(path="C:/workspace/pea/verify/shots/popup_test.png")
        print("截图保存到: C:/workspace/pea/verify/shots/popup_test.png")

        # 验证模型选择弹出层
        model_btn = page.locator(".node-input-model-chip").first
        print(f"找到模型按钮数量: {model_btn.count()}")
        if model_btn.count() > 0:
            btn_box = model_btn.bounding_box()
            print(f"模型按钮位置: x={btn_box['x']:.0f}, y={btn_box['y']:.0f}, h={btn_box['height']:.0f}")
            
            # 点击前记录所有按钮位置
            all_btns = page.locator("button").all()
            print(f"页面上共有 {len(all_btns)} 个按钮")
            
            model_btn.click()
            page.wait_for_timeout(500)

            # 检查弹出层 DOM 结构
            picker_html = page.evaluate("""() => {
                const picker = document.querySelector('.node-model-picker');
                if (!picker) return 'NOT_FOUND';
                const style = getComputedStyle(picker);
                return JSON.stringify({
                    left: picker.style.left,
                    top: picker.style.top,
                    computedLeft: style.left,
                    computedTop: style.top,
                    transform: style.transform,
                    parentClass: picker.parentElement?.className
                });
            }""")
            print(f"弹出层样式信息: {picker_html}")

            picker = page.locator(".node-model-picker")
            if picker.count() > 0:
                picker_box = picker.bounding_box()
                print(f"弹出层位置: x={picker_box['x']:.0f}, y={picker_box['y']:.0f}, h={picker_box['height']:.0f}")
                
                # 检查弹出层是否在按钮上方
                is_above = picker_box['y'] + picker_box['height'] <= btn_box['y'] + 10  # 允许10px误差
                # 检查间距是否合理（应该紧贴，最多10px）
                distance = btn_box['y'] - (picker_box['y'] + picker_box['height'])
                horizontal_aligned = abs(picker_box['x'] - btn_box['x']) < 50  # 左对齐允许50px误差
                
                print(f"[模型选择] 弹出层在按钮上方: {is_above}")
                print(f"[模型选择] 弹出层与按钮间距: {distance:.0f}px")
                print(f"[模型选择] 水平对齐偏差: {abs(picker_box['x'] - btn_box['x']):.0f}px")
                
                if is_above and horizontal_aligned and distance <= 10:
                    print("[模型选择] ✅ PASS - 弹出层紧贴按钮上方")
                else:
                    print(f"[模型选择] ❌ FAIL - 位置不对 (间距={distance:.0f}px)")
            else:
                print("❌ 未找到模型选择弹出层")
            
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        else:
            print("❌ 未找到模型选择按钮")

        # 验证比例选择弹出层
        # 先关闭模型选择弹出层
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        
        aspect_btn = page.locator(".node-input-aspect-chip").first
        print(f"\n找到比例按钮数量: {aspect_btn.count()}")
        
        # 如果找不到，列出所有按钮的 class
        if aspect_btn.count() == 0:
            all_btns_info = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('button')).slice(0, 20).map(b => ({
                    className: b.className,
                    text: b.textContent?.slice(0, 30)
                }));
            }""")
            print("前 20 个按钮信息:")
            for i, btn in enumerate(all_btns_info):
                print(f"  {i}: {btn['className']} - {btn['text']}")
        elif aspect_btn.count() > 0:
            btn_box = aspect_btn.bounding_box()
            print(f"\n比例按钮位置: x={btn_box['x']:.0f}, y={btn_box['y']:.0f}, h={btn_box['height']:.0f}")
            
            aspect_btn.click()
            page.wait_for_timeout(500)

            picker = page.locator(".node-aspect-picker")
            if picker.count() > 0:
                picker_box = picker.bounding_box()
                print(f"弹出层位置: x={picker_box['x']:.0f}, y={picker_box['y']:.0f}, h={picker_box['height']:.0f}")
                
                is_above = picker_box['y'] + picker_box['height'] <= btn_box['y'] + 5
                horizontal_aligned = abs(picker_box['x'] - btn_box['x']) < 50
                
                print(f"[比例选择] 弹出层在按钮上方: {is_above}")
                print(f"[比例选择] 水平对齐偏差: {abs(picker_box['x'] - btn_box['x']):.0f}px")
                
                if is_above and horizontal_aligned:
                    print("[比例选择] ✅ PASS - 弹出层在按钮上方且左对齐")
                else:
                    print(f"[比例选择] ❌ FAIL - 位置不对")
            else:
                print("❌ 未找到比例选择弹出层")
        else:
            print("❌ 未找到比例选择按钮")

        print(f"\n控制台错误: {len(errors)}")
        if errors:
            for e in errors[:3]:
                print(f"  - {e[:80]}")

        browser.close()

if __name__ == "__main__":
    main()
