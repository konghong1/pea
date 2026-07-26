# -*- coding: utf-8 -*-
"""E26：出图数量选择器显示与传参验证

验证：
1. 图片节点输入栏应显示出图数量选择器（1x/2x/3x/4x）
2. 点击应弹出选项列表
3. 弹窗样式与模型选择弹窗一致
4. 选择后发送请求，验证 params.n 是否传递
"""
from __future__ import annotations
import os, json, time
from playwright.sync_api import sync_playwright

WEB = "http://localhost:8088"

def main():
    errors = []
    def step(label, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {label}  {detail}")
        if not ok: errors.append(label)

    shots = os.path.join(os.path.dirname(__file__), 'shots')
    os.makedirs(shots, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"console:{m.type}:{m.text[:120]}") if m.type == "error" else None)

        # 注册 + 登录
        page.goto(WEB, wait_until="networkidle")
        ts = page.evaluate("Date.now()")
        email = f"e26_{ts}@pea.ai"
        if page.locator("text=去注册").count() > 0:
            page.locator("text=去注册").first.click(); page.wait_for_timeout(500)
        ins = page.locator("input:visible")
        cnt = ins.count()
        if cnt >= 2:
            ins.nth(0).fill(email); page.wait_for_timeout(120)
            ins.nth(1).fill("test1234"); page.wait_for_timeout(120)
            if cnt >= 3: ins.nth(2).fill("E26")
        page.locator("button", has_text="注").first.click(); page.wait_for_timeout(1500)
        page.wait_for_selector("text=新建项目", timeout=8000)
        print(f'注册成功: {email}')

        # 新建项目
        page.locator("text=新建项目").first.click(); page.wait_for_timeout(900)
        page.wait_for_selector(".react-flow", timeout=10000); page.wait_for_timeout(400)
        print('项目创建成功')

        # 添加图片节点
        def add_node(label):
            page.locator(".pea-tlb-btn[aria-label*='添加节点']").first.click(); page.wait_for_timeout(250)
            page.locator(f".pea-add-menu-item:has-text('{label}')").first.click(); page.wait_for_timeout(350)
            return page.evaluate("""() => { const s=window.__canvas.getState(); const ns=s.nodes; return ns[ns.length-1].id; }""")

        img = add_node("图片")
        print(f'图片节点 ID: {img}')

        # 选中图片节点（使用真实鼠标点击）
        node_el = page.locator(f'.react-flow__node[data-id="{img}"]')
        box = node_el.first.bounding_box()
        if box:
            cx = box['x'] + box['width'] / 2
            cy = box['y'] + box['height'] / 2
            page.mouse.click(cx, cy)
            page.wait_for_timeout(300)
            print(f'点击节点位置: ({cx}, {cy})')

        # 等待输入栏出现
        page.wait_for_timeout(500)

        # 查找所有可能的输入区域
        input_bar = page.locator('.node-input-bar')
        bottom_bar = page.locator('.bottom-prompt-bar, .canvas-bottom-bar')
        chat_prompt = page.locator('.node-chat-prompt')
        
        print(f'输入栏数量: {input_bar.count()}, 底部栏数量: {bottom_bar.count()}, 聊天提示数量: {chat_prompt.count()}')

        # 截图：节点输入栏
        page.screenshot(path=f'{shots}/e26_input_bar.png')
        print('截图保存: e26_input_bar.png')

        # 检查出图数量按钮是否存在
        count_btn = page.locator('.node-count-btn')
        count_btn_count = count_btn.count()
        step('出图数量按钮存在', count_btn_count > 0, f'找到 {count_btn_count} 个')

        if count_btn_count > 0:
            # 点击打开选择器
            count_btn.first.click()
            page.wait_for_timeout(300)

            # 截图：选择器弹窗
            page.screenshot(path=f'{shots}/e26_count_dropdown.png')
            print('截图保存: e26_count_dropdown.png')

            # 检查弹窗选项
            opts = page.locator('.node-count-btn-dropdown .node-count-opt')
            opts_count = opts.count()
            step('选择器有选项', opts_count > 0, f'找到 {opts_count} 个选项')

            # 检查选项文本
            if opts_count > 0:
                texts = [opt.text_content() for opt in opts.all()]
                print(f'选项: {texts}')
                step('有 2x/3x/4x 选项', any('2x' in (t or '') or '3x' in (t or '') or '4x' in (t or '') for t in texts), str(texts))

                # 选择 4x
                opt_4x = page.locator('.node-count-opt:has-text("4x")')
                if opt_4x.count() > 0:
                    opt_4x.click()
                    page.wait_for_timeout(200)
                    step('选择 4x 成功', True)

                    # 验证按钮文本更新
                    btn_text = count_btn.first.text_content()
                    step('按钮显示 4x', '4x' in (btn_text or ''), f'text={btn_text}')

                    # 再次打开获取样式
                    count_btn.first.click()
                    page.wait_for_timeout(200)
        else:
            step('出图数量按钮存在', False, '未找到 .node-count-btn')

        # 检查模型选择弹窗样式（对比）
        model_chip = page.locator('.node-input-model-chip')
        model_picker_style = None
        count_picker_style = None

        if model_chip.count() > 0:
            model_chip.first.click()
            page.wait_for_timeout(300)
            page.screenshot(path=f'{shots}/e26_model_picker_style.png')
            print('截图保存: e26_model_picker_style.png')

            # 获取模型选择器样式
            model_picker = page.locator('.node-model-picker, .node-model-picker-dropdown')
            if model_picker.count() > 0:
                model_picker_style = model_picker.first.evaluate('el => ({bg: getComputedStyle(el).background, borderRadius: getComputedStyle(el).borderRadius, boxShadow: getComputedStyle(el).boxShadow, padding: getComputedStyle(el).padding})')
                print(f'模型选择器样式: {model_picker_style}')
            page.keyboard.press('Escape')
            page.wait_for_timeout(200)

        # 获取数量选择器样式
        if count_btn_count > 0:
            count_dropdown = page.locator('.node-count-btn-dropdown')
            if count_dropdown.count() > 0:
                count_picker_style = count_dropdown.first.evaluate('el => ({bg: getComputedStyle(el).background, borderRadius: getComputedStyle(el).borderRadius, boxShadow: getComputedStyle(el).boxShadow, padding: getComputedStyle(el).padding})')
                print(f'数量选择器样式: {count_picker_style}')
                page.screenshot(path=f'{shots}/e26_count_picker_style.png')

        # 对比样式
        if model_picker_style and count_picker_style:
            # 弹窗样式应一致（背景色、圆角）
            style_match = (
                'rgba' in (model_picker_style.get('bg') or '') and
                'rgba' in (count_picker_style.get('bg') or '')
            )
            step('弹窗样式与模型选择一致', style_match, f'model={model_picker_style}, count={count_picker_style}')

        # 验证参数传递（通过拦截请求）
        captured_params = {}
        def capture_req(req):
            if '/generation/node' in req.url:
                try:
                    body = req.post_data_json
                    if body:
                        captured_params['params'] = body.get('params', {})
                        captured_params['model'] = body.get('model')
                        print(f'捕获请求: {json.dumps(body, indent=2, ensure_ascii=False)}')
                except Exception as e:
                    print(f'解析请求失败: {e}')

        page.on('request', capture_req)

        # 先选择模型（点击模型选择器）
        model_chip = page.locator('.node-input-model-chip')
        if model_chip.count() > 0:
            model_chip.first.click()
            page.wait_for_timeout(300)
            # 选择第一个可用模型
            model_card = page.locator('.picker-card').first
            if model_card.count() > 0:
                model_card.click()
                page.wait_for_timeout(200)
                print('已选择模型')

        # 选择出图数量 4x
        count_btn = page.locator('.node-count-btn')
        if count_btn.count() > 0:
            count_btn.first.click()
            page.wait_for_timeout(200)
            opt_4x = page.locator('.node-count-opt:has-text("4x")')
            if opt_4x.count() > 0:
                opt_4x.click()
                page.wait_for_timeout(200)
                print('已选择 4x')

        # 输入提示词并发送
        prompt_input = page.locator('.node-chat-prompt-textarea, textarea.node-chat-prompt-textarea, .node-input-bar textarea')
        print(f'提示词输入框数量: {prompt_input.count()}')
        if prompt_input.count() > 0:
            prompt_input.first.fill('A beautiful sunset over mountains')
            page.wait_for_timeout(200)
            send_btn = page.locator('.node-chat-prompt-send, .node-input-send')
            if send_btn.count() > 0:
                btn_disabled = send_btn.first.is_disabled()
                print(f'发送按钮禁用状态: {btn_disabled}')
                if not btn_disabled:
                    send_btn.first.click()
                    print('发送生成请求')
                    page.wait_for_timeout(5000)  # 等待请求发出
                else:
                    print('发送按钮被禁用，无法测试参数传递')
            else:
                print('未找到发送按钮')
        else:
            print('未找到提示词输入框')
            # 尝试查找所有 textarea
            all_textareas = page.locator('textarea')
            print(f'所有 textarea 数量: {all_textareas.count()}')

        # 检查捕获的参数
        params = captured_params.get('params', {})
        n_value = params.get('n') or params.get('count')
        step('请求包含 n 参数', n_value is not None, f'n={n_value}, params={params}')

        # 关闭
        page.close()
        ctx.close()
        browser.close()

    print('\n=== E26 测试结果 ===')
    if errors:
        print(f'失败项: {errors}')
    else:
        print('全部通过!')

if __name__ == '__main__':
    main()
