"""
验证修复：生成中动画完整显示 + 提示词不再泄露
参考 screenshot_generating_state.py 的成熟登录+注入模式
"""
import asyncio
import uuid
from playwright.async_api import async_playwright
from pathlib import Path

BASE = "http://localhost:8088"
OUT = Path(r'C:\workspace\pea\verify\shot_generating_fix.png')
OUT.parent.mkdir(parents=True, exist_ok=True)

async def main():
    email = f"genfix_{uuid.uuid4().hex[:8]}@pea.ai"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        await page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

        # 注册 + 登录
        print('正在注册/登录...')
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(800)
        if await page.locator('text=没有账号？去注册').count() > 0:
            await page.locator('text=没有账号？去注册').first.click()
            await page.wait_for_timeout(400)
        await page.fill('input[placeholder="you@pea.ai"]', email)
        await page.fill('input[placeholder="至少 8 位"]', 'test1234')
        await page.fill('input[placeholder="可选"]', 'verify')
        await page.locator('form button[type=submit]').click()
        await page.wait_for_timeout(2000)

        token = await page.evaluate("localStorage.getItem('pea_token')")
        print(f'Token: {"OK" if token else "FAIL"}')

        if not token:
            await page.screenshot(path=str(OUT))
            print('登录失败')
            await browser.close()
            return

        # 创建画布
        cid = await page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {
                method: 'POST',
                headers: {'Content-Type': 'application/json',
                          ...(token ? {Authorization: `Bearer ${token}`} : {})},
                body: JSON.stringify({name: 'genfix_verify'})
            });
            const d = await r.json();
            return d.id || d.canvas?.id;
        }""")
        print(f'画布 ID: {cid}')

        # 注入生成中的图片节点（模拟点击生成后的状态）
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(800)
        await page.evaluate("""async (cid) => {
            const store = window.__canvas;
            if (store) {
                await store.getState().openCanvas(cid);
            }
            store.setState({
                nodes: [{
                    id: 'nImgGen',
                    type: 'pea',
                    position: {x: 420, y: 240},
                    data: {
                        kind: 'image',
                        label: 'Image',
                        prompt: '一只可爱的猫咪在阳光下打盹，毛茸茸的，温暖的光线，高质量',
                        params: { aspect_ratio: '16:9' },
                        generating: true,
                        error: undefined,
                        resultUrl: undefined,
                        resultUrls: undefined
                    }
                }],
                edges: [],
                version: 1,
                dirty: true,
            });
            if (store.getState().select) store.getState().select('nImgGen');
            const ui = window.__ui;
            if (ui) ui.getState().setActive('canvas');
        }""", cid)
        await page.wait_for_timeout(1500)

        # ===== DOM 探针验证 =====
        results = {}

        # 1. 节点是否有 is-generating 类
        has_gen_class = await page.evaluate("""() => {
            const node = document.querySelector('.pea-node.is-generating');
            return !!node;
        }""")
        results['has-is-generating'] = has_gen_class
        print(f'is-generating 类: {"✅" if has_gen_class else "❌"}')

        # 2. body-card overflow 状态
        ov = await page.evaluate("""() => {
            const node = document.querySelector('.pea-node.is-generating');
            if (!node) return 'no-node';
            const body = node.querySelector('.pea-node-body-card');
            if (!body) return 'no-body';
            return getComputedStyle(body).overflow;
        }""")
        results['overflow'] = ov
        print(f'Body card overflow: {ov} {"✅" if ov == "visible" else "❌ 需要 visible"}')

        # 3. 提示词回显是否可见
        prompt_info = await page.evaluate("""() => {
            // 在生成中的节点内查找提示词回显
            const genNode = document.querySelector('.pea-node.is-generating');
            if (!genNode) return { error: 'no-gen-node' };
            const echoes = genNode.querySelectorAll('.pea-node-prompt-echo');
            let visible = 0;
            echoes.forEach(e => {
                const s = getComputedStyle(e);
                if (s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0') visible++;
            });
            return { total_in_gen_node: echoes.length, visible };
        }""")
        results['prompt-echo-in-gen'] = prompt_info
        print(f'生成节点内提示词: 可见={prompt_info.get("visible", "?")} {"✅ 无泄露" if prompt_info.get("visible", 1) == 0 else "❌ 泄露!"}')

        # 4. TechLoader 动画面板信息
        loader_info = await page.evaluate("""() => {
            const panel = document.querySelector('.pea-node-generating');
            if (!panel) return { exists: false };
            const rect = panel.getBoundingClientRect();
            const svg = panel.querySelector('.tech-loader__svg');
            const label = panel.querySelector('.tech-loader__label');
            return {
                exists: true,
                size: { w: Math.round(rect.width), h: Math.round(rect.height) },
                hasSvg: !!svg,
                hasLabel: !!label,
                labelText: label ? label.textContent.trim() : null,
                overflow: getComputedStyle(panel).overflow
            };
        }""")
        results['loader'] = loader_info
        print(f'TechLoader: {loader_info.get("size", {})} svg={loader_info.get("hasSvg")} label={loader_info.get("labelText")}')

        # 5. 检查整个媒体卡片内的子元素结构（确认无提示词）
        structure = await page.evaluate("""() => {
            const genNode = document.querySelector('.pea-node.is-generating');
            if (!genNode) return null;
            const card = genNode.querySelector('.pea-node-media-card');
            if (!card) return 'no-media-card';
            return Array.from(card.children).map(c => ({
                tag: c.tagName,
                cls: c.className.toString().substring(0, 80),
                text: c.textContent.substring(0, 50)
            }));
        }""")
        results['media-card-structure'] = structure
        print(f'媒体卡片子元素: {structure}')

        # 截图
        await page.screenshot(path=str(OUT), full_page=False)
        print(f'\n截图保存: {OUT}')

        # 总结
        print('\n' + '='*40)
        passes = 0
        total = 4

        if ov == 'visible':
            print('✅ 1/4 overflow:visible - 动画不被裁切')
            passes += 1
        else:
            print(f'❌ 1/4 overflow={ov} (应为visible)')

        if prompt_info.get('visible', 1) == 0:
            print('✅ 2/4 提示词不泄露')
            passes += 1
        else:
            print(f'❌ 2/4 仍有 {prompt_info.get("visible")} 个可见提示词')

        if loader_info.get('hasSvg') and loader_info.get('hasLabel'):
            print(f'✅ 3/4 TechLoader 动画完整 ({loader_info["size"]})')
            passes += 1
        else:
            print('❌ 3/4 TechLoader 缺失')

        # 检查结构中无 pea-node-prompt-echo
        has_echo = any('prompt-echo' in str(s) for s in (structure or []))
        if not has_echo:
            print('✅ 4/4 媒体卡片结构干净（无提示词）')
            passes += 1
        else:
            print('❌ 4/4 媒体卡片仍含提示词元素')

        print(f'\n{"🎉 全部通过" if passes == total else f"⚠️ {passes}/{total} 通过"}')
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
