"""E28 - 出图数量端到端验证"""
import json, time, sys, os, re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:8088"
BFF = "http://localhost:4100"
shots = Path(__file__).parent / "shots"
shots.mkdir(exist_ok=True)

def ts_email() -> str:
    return f"e{int(time.time())%1000000}@pea.ai"

def step(name: str, passed: bool, detail: str = ""):
    icon = "PASS" if passed else "FAIL"
    print(f"  [{icon}] {name}{' — ' + detail if detail else ''}")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(locale="zh-CN")
        page = ctx.new_page()
        page.set_default_timeout(15000)
        page.add_init_script("window.__peaDevHooks=1;")
        page.goto(BASE)
        email = ts_email()
        page.goto(f"{BASE}/register")
        page.wait_for_timeout(500)
        # 等待注册表单出现
        page.wait_for_timeout(3000)
        # 截图查看当前页面状态
        page.screenshot(path=f'{shots}/e28_page_state.png')
        
        # 检查是否有 email 输入框 - 使用占位符选择器
        all_inputs = page.locator('input')
        print(f"总共找到 {all_inputs.count()} 个输入框")
        
        if all_inputs.count() >= 2:
            email_input = all_inputs.first
            pass_input = all_inputs.last
            
            email_input.fill(email)
            print("[OK] 成功填写 email")
            
            pass_input.fill("Test123456!")
            print("[OK] 成功填写密码")
        else:
            print("[FAIL] 输入框数量不足，退出测试")
            browser.close()
            return
        
        submit_btn = page.locator('button[type="submit"]').first
        if submit_btn.count() > 0:
            submit_btn.click()
        else:
            print("[WARN] 未找到 submit 按钮")
            browser.close()
            return
        try:
            page.wait_for_url("**/workspace", timeout=8000)
            print(f"[OK] 注册成功，已到达 workspace")
        except Exception:
            # 检查当前 URL - 可能重定向到 login
            current_url = page.url
            print(f"[INFO] 当前 URL: {current_url}")
            if "/login" in current_url or "/register" in current_url:
                print("[WARN] 仍在登录页面，尝试手动登录...")
                # 等待表单显示
                page.wait_for_timeout(2000)
                # 重新填写并点击登录
                all_inputs = page.locator('input')
                if all_inputs.count() >= 2:
                    all_inputs.first.fill(email)
                    all_inputs.last.fill("Test123456!")
                    submit_btn = page.locator('button[type="submit"], button:has-text("登录"), button:has-text("Register")')
                    if submit_btn.count() > 0:
                        submit_btn.first.click()
                        try:
                            page.wait_for_url("**/workspace", timeout=8000)
                            print(f"[OK] 登录成功")
                        except Exception:
                            print(f"[WARN] 登录后仍在: {page.url}")
                            browser.close()
                            return
                else:
                    print("[FAIL] 输入框数量不足")
                    browser.close()
                    return
            elif "/workspace" not in current_url:
                print(f"[WARN] 未在预期 URL 找到: {current_url}")
                browser.close()
                return

        # 创建项目
        page.click('button:has-text("新建项目")')
        page.wait_for_timeout(300)
        page.fill('input[placeholder*="项目名"], input[type="text"]', "E28 Test")
        page.wait_for_timeout(200)
        create_btn = page.locator('button:has-text("创建"), button:has-text("新建")')
        if create_btn.count() > 0:
            create_btn.first.click()
            page.wait_for_timeout(500)
        try:
            page.wait_for_selector('.project-card', timeout=5000)
        except Exception:
            print("[WARN] 未找到项目卡片")
            browser.close()
            return
        
        proj_cards = page.locator('.project-card')
        if proj_cards.count() == 0:
            print("[FAIL] 无项目卡片")
            browser.close()
            return
        
        first_card = proj_cards.first
        first_card.click()
        page.wait_for_timeout(1000)
        
        # 添加图片节点
        page.click('[aria-label*="添加节点"], [aria-label*="Add"], .pea-tlb-btn')
        page.wait_for_timeout(300)
        img_add = page.locator('[data-action="add-image"], [data-type="image"], :text("图片")')
        if img_add.count() > 0:
            img_add.first.click()
            page.wait_for_timeout(800)
        else:
            page.click(':text("图片")')
            page.wait_for_timeout(800)
        
        try:
            page.wait_for_selector('.react-flow__node[data-kind="image"]', timeout=5000)
        except Exception:
            print("[WARN] 未找到 image 节点，直接退出")
            browser.close()
            return
        
        img_id = page.evaluate("""() => {
            const s = window.__canvas.getState();
            const ns = s.nodes;
            for (const n of ns) {
                if (n.data.kind === 'image' || (n.type || '').includes('image')) {
                    return n.id;
                }
            }
            return null;
        }""")
        print(f"图片节点 ID: {img_id}")
        if not img_id:
            print("[FAIL] 未找到图片节点")
            browser.close()
            return
        
        # 选中图片节点
        node_locator = page.locator(f'.react-flow__node[data-id="{img_id}"]')
        if node_locator.count() > 0:
            box = node_locator.bounding_box()
            if box:
                page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                page.wait_for_timeout(500)
        
        selected_id = page.evaluate("""() => {
            const s = window.__canvas.getState();
            return s.selectedId || (s.selectedIds && s.selectedIds[0]);
        }""")
        step("节点已被选中", selected_id == img_id, f"selectedId={selected_id}")
        
        # 检查出图数量选择器
        count_btn = page.locator('.node-count-btn')
        step("出图数量选择器已显示", count_btn.count() > 0, f"count={count_btn.count()}")
        if count_btn.count() > 0:
            btn_text = count_btn.first.text_content() or ""
            step("按钮默认显示 1x", "1" in btn_text, f"text='{btn_text}'")
            
            count_btn.first.click()
            page.wait_for_timeout(300)
            
            dropdown = page.locator('.node-count-btn-dropdown')
            step("下拉列表已展开", dropdown.count() > 0, f"count={dropdown.count()}")
            
            if dropdown.count() > 0:
                opts = dropdown.locator('.node-count-opt')
                count_opts = opts.count()
                step("选项完整", count_opts == 4, f"有{count_opts}个选项")
                
                for i in range(min(count_opts, 4)):
                    text = opts.nth(i).text_content() or ""
                    step(f"选项{i+1} 存在", any(c in text for c in ['1x', '2x', '3x', '4x']), f"text='{text}'")
                
                # 选择 3x
                opts_3x = dropdown.locator(':text("3x"), :text("3 张")')
                if opts_3x.count() > 0:
                    opts_3x.first.click()
                    page.wait_for_timeout(300)
                    
                    new_text = count_btn.first.text_content() or ""
                    step("选择 3x 后显示 3x", "3" in new_text and "x" in new_text, f"text='{new_text}'")
                    
                    current_count = page.evaluate("""() => {
                        const s = window.__canvas.getState();
                        const n = s.nodes.find(nd => nd.data.kind === 'image' && nd.id === s.selectedId);
                        if (!n) return null;
                        return {
                            count: n.data.count || 1,
                            kind: n.data.kind
                        };
                    }""")
                    step("params.n 值正确", current_count and 'count' in current_count and current_count['count'] == 3, f"value={current_count}")
        
        page.screenshot(path=f'{shots}/e28_count_selector.png')
        print(f"截图保存: e28_count_selector.png")
        browser.close()
        print("\n[总结] E28 测试完成，主要验证 UI 交互，不依赖网络请求。")

if __name__ == "__main__":
    main()
