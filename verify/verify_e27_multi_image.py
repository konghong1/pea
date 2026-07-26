"""E27 - 出图数量功能验证（简化版）
验证：
1. 出图数量选择器显示正确
2. 参数 n 正确传递
3. Mock 模式下生成对应数量的图片
"""
from playwright.sync_api import sync_playwright
from pathlib import Path

BASE = "http://localhost:8088"
shots = Path(__file__).parent / "shots"
shots.mkdir(exist_ok=True)

def main():
    errors = []
    def step(label, ok, detail=""):
        mark = "✅" if ok else "❌"
        print(f"{mark} {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            errors.append(label)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"console:{m.type}:{m.text[:120]}") if m.type == "error" else None)

        # 访问首页并注册
        page.goto(BASE, wait_until="networkidle")
        ts = page.evaluate("Date.now()")
        email = f"e27_{ts}@pea.ai"

        if page.locator("text=去注册").count() > 0:
            page.locator("text=去注册").first.click()
            page.wait_for_timeout(500)

        ins = page.locator("input:visible")
        cnt = ins.count()
        if cnt >= 2:
            ins.nth(0).fill(email)
            page.wait_for_timeout(120)
            ins.nth(1).fill("test1234")
            page.wait_for_timeout(120)

        page.locator("button", has_text="注").first.click()
        page.wait_for_timeout(1500)
        page.wait_for_selector("text=新建项目", timeout=8000)

        # 创建项目
        page.locator("text=新建项目").first.click()
        page.wait_for_timeout(900)
        page.wait_for_selector(".react-flow", timeout=10000)
        page.wait_for_timeout(400)

        # 添加图片节点
        def add_node(label):
            page.locator(".pea-tlb-btn[aria-label*='添加节点']").first.click()
            page.wait_for_timeout(250)
            page.locator(f".pea-add-menu-item:has-text('{label}')").first.click()
            page.wait_for_timeout(350)
            return page.evaluate("""() => {
                const s = window.__canvas.getState();
                const ns = s.nodes;
                return ns[ns.length-1].id;
            }""")

        img = add_node("图片")
        print(f"图片节点 ID: {img}")

        # 在操作之前设置请求拦截
        captured = {}
        def capture_req(req):
            if '/generation/node' in req.url:
                try:
                    body = req.post_data_json
                    if body:
                        captured['n'] = body.get('params', {}).get('n')
                        captured['model'] = body.get('model')
                        print(f"  捕获请求: n={captured.get('n')}, model={captured.get('model')}")
                except Exception as e:
                    print(f"  解析请求失败: {e}")

        page.on('request', capture_req)

        # 等待节点渲染
        page.wait_for_timeout(300)

        # 选中图片节点 - 点击节点中心
        node = page.locator(f'.react-flow__node[data-id="{img}"]')
        box = node.bounding_box()
        if box:
            page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.wait_for_timeout(500)

        # 验证节点选中状态
        selected_id = page.evaluate("""() => {
            const s = window.__canvas.getState();
            return s.selectedId || (s.selectedIds && s.selectedIds[0]);
        }""")
        step("节点已被选中", selected_id == img, f"selectedId={selected_id}")

        # 截图检查
        page.screenshot(path=f'{shots}/e27_after_select.png')

        # 检查 NodeChatPrompt 组件是否渲染（检查输入框）
        textarea = page.locator('textarea.node-input-textarea, textarea.node-chat-prompt-input')
        step("输入框已显示", textarea.count() > 0, f"count={textarea.count()}")
        count_btn = page.locator('.node-count-btn')
        step("出图数量按钮已显示", count_btn.count() > 0, f"count={count_btn.count()}")

        if count_btn.count() > 0:
            # 点击打开下拉菜单
            count_btn.first.click()
            page.wait_for_timeout(300)
            page.screenshot(path=f'{shots}/e27_count_dropdown.png')

            # 检查选项
            options = page.locator('.node-count-opt')
            opt_count = options.count()
            step("下拉菜单有选项", opt_count >= 3, f"选项数={opt_count}")

            # 选择 3x
            opt_3x = page.locator('.node-count-opt:has-text("3")')
            if opt_3x.count() > 0:
                opt_3x.first.click()
                page.wait_for_timeout(200)
                step("已选择 3x", True)

                # 检查按钮文本更新
                btn_text = count_btn.first.text_content()
                step("按钮显示 3x", "3" in (btn_text or ""), f"text={btn_text}")

        # 查找并选择模型（如果需要）
        model_btn = page.locator('.node-model-btn')
        if model_btn.count() > 0:
            model_btn.first.click()
            page.wait_for_timeout(300)
            first_model = page.locator('.node-model-picker-item').first
            if first_model.count() > 0:
                first_model.click()
                page.wait_for_timeout(300)
                print("已选择模型")

        # 查找输入框（正确类名）
        textarea = page.locator('textarea.node-input-textarea, textarea.node-chat-prompt-input')
        step("输入框已显示", textarea.count() > 0, f"count={textarea.count()}")

        if textarea.count() > 0:
            textarea.first.fill("Test multi-image generation")
            page.wait_for_timeout(200)

            # 点击发送（正确类名）
            send_btn = page.locator('button.node-input-send, button.node-chat-prompt-send')
            step("发送按钮已显示", send_btn.count() > 0, f"count={send_btn.count()}")

            if send_btn.count() > 0:
                btn = send_btn.first
                is_disabled = btn.is_disabled()
                step("发送按钮可用", not is_disabled)

                if not is_disabled:
                    btn.click()
                    print("已发送生成请求")
                    page.wait_for_timeout(3000)  # 等待请求发出
                else:
                    print("发送按钮被禁用")
            else:
                print("未找到发送按钮")
        else:
            print("未找到输入框")

        # 验证参数
        step("请求包含 n=3", captured.get('n') == 3, f"n={captured.get('n')}")

        # 等待生成完成（Mock 模式很快）
        print("等待生成完成...")
        for i in range(30):
            result = page.evaluate("""(id) => {
                const s = window.__canvas.getState();
                const node = s.nodes.find(n => n.id === id);
                return {
                    urls: node?.data?.resultUrls || [],
                    generating: node?.data?.generating
                };
            }""", img)
            if len(result.get('urls', [])) > 0:
                print(f"  生成完成，图片数={len(result['urls'])}")
                break
            if i >= 10 and not result.get('generating'):
                print("  未检测到生成中状态，继续等待...")
            page.wait_for_timeout(1000)

        # 检查结果
        result = page.evaluate("""(id) => {
            const s = window.__canvas.getState();
            const node = s.nodes.find(n => n.id === id);
            return {
                urls: node?.data?.resultUrls || [],
                index: node?.data?.resultIndex
            };
        }""", img)

        url_count = len(result.get('urls', []))
        step(f"生成了 {url_count} 张图", url_count == 3, f"urls={result.get('urls', [])[:2]}...")

        # 检查多图角标
        if url_count > 1:
            badge = page.locator(f'.react-flow__node[data-id="{img}"] .pea-node-image-badge-btn')
            step("多图角标已显示", badge.count() > 0)

            if badge.count() > 0:
                badge_text = badge.first.text_content()
                step("角标显示数量", str(url_count) in (badge_text or ""), f"text={badge_text}")

                # 点击展开选择器
                badge.first.click()
                page.wait_for_timeout(300)
                page.screenshot(path=f'{shots}/e27_image_picker.png')

                picker_items = page.locator('.pea-node-image-picker-item')
                step(f"选择器有 {picker_items.count()} 张缩略图", picker_items.count() == url_count)

        step("无 console error", len([e for e in errors if e.startswith('console:')]) == 0, f"errors={errors[:3]}")

        browser.close()

    if errors:
        print(f"\n❌ 失败项: {errors}")
        return 1
    else:
        print("\n🎉 E27 全部通过")
        return 0

if __name__ == "__main__":
    exit(main())
