"""
探测：点击生成后提示词是否消失 + 浅色下控制条可见性
"""
import asyncio, sys, json
sys.path.insert(0, r'C:\workspace\pea')
from playwright.async_api import async_playwright

URL = 'http://localhost:8088'
EMAIL = 'v3test@test.com'
PWD = 'Test123456'

def log(msg): print(f'[LOG] {msg}')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        
        await page.goto(URL, wait_until='networkidle', timeout=20000)
        await asyncio.sleep(1)
        
        # 登录
        await page.fill('input[placeholder*="you@"]', EMAIL)
        await page.fill('input[placeholder*="至少"]', PWD)
        await page.press('input[placeholder*="至少"]', 'Enter')
        await asyncio.sleep(3)
        
        # 点击第一个 prompt_probe 画布卡片进入编辑器
        log('点击画布卡片...')
        try:
            card = page.locator('text=prompt_probe').first
            await card.click()
            await asyncio.sleep(3)
        except Exception as e:
            log(f'点击失败: {e}')
        
        cur_url = page.url
        log(f'当前 URL: {cur_url}')
        
        # 检查 store 是否可用
        store_info = await page.evaluate("""() => {
            const s = window.__canvas;
            if (!s) return { hasStore: false };
            const st = s.getState();
            return {
                hasStore: true,
                hasSetState: typeof st.setState === 'function',
                hasNodes: Array.isArray(st.nodes),
                nodeCount: st.nodes ? st.nodes.length : -1,
            };
        }""")
        log(f'Store: {json.dumps(store_info)}')
        
        if not store_info.get('hasStore'):
            log('Store 不可用，截图查看当前页面...')
            await page.screenshot(path=r'C:\workspace\pea\verify\shot_probe_nostore.png', full_page=False)
            await browser.close()
            return
        
        # 注入视频节点 + 选中（非生成状态）
        log('注入视频节点...')
        await page.evaluate("""() => {
            const store = window.__canvas;
            const nid = 'vid_probe';
            store.setState({
                nodes: [{
                    id: nid,
                    type: 'pea',
                    position: {x: 400, y: 300},
                    data: {
                        kind: 'video',
                        label: 'Video',
                        prompt: '',
                        meta: { editorText: '<p>一只可爱的小猫在草地上奔跑</p>' },
                        generating: false,
                        error: undefined,
                        resultUrl: undefined,
                        resultUrls: undefined,
                    }
                }],
                edges: [],
                version: 1,
                dirty: true,
                selectedIds: [nid]
            });
            if (store.getState().setActive) store.getState().setActive('canvas');
        }""")
        await asyncio.sleep(2)
        
        # 截图 + 检查生成前状态
        await page.screenshot(path=r'C:\workspace\pea\verify\shot_prompt_before_gen.png', full_page=False)
        log('截图: 生成前')
        
        editor_text = await page.evaluate("""() => {
            const ed = document.querySelector('.node-prompt-editor');
            if (!ed) return { exists: false };
            return { 
                exists: true, 
                text: ed.innerText, 
                htmlLen: ed.innerHTML.length,
                color: window.getComputedStyle(ed).color 
            };
        }""")
        log(f'生成前输入框: text="{editor_text.get("text", "N/A")}" color={editor_text.get("color")}')
        
        input_bar = await page.evaluate("""() => {
            const bar = document.querySelector('.node-input-bar');
            if (!bar) return { exists: false };
            const cs = window.getComputedStyle(bar);
            return { exists: true, display: cs.display, visibility: cs.visibility, opacity: cs.opacity };
        }""")
        log(f'生成前输入栏: {input_bar}')
        
        # 切换到 generating 状态
        log('>>> 切换到 generating 状态...')
        await page.evaluate("""() => {
            const store = window.__canvas;
            store.getState().updateNodeData('vid_probe', { generating: true });
        }""")
        await asyncio.sleep(2)
        
        # 截图 + 检查生成中状态
        await page.screenshot(path=r'C:\workspace\pea\verify\shot_prompt_during_gen.png', full_page=False)
        log('截图: 生成中')
        
        editor_text2 = await page.evaluate("""() => {
            const ed = document.querySelector('.node-prompt-editor');
            if (!ed) return { exists: false };
            const bar = ed.closest('.node-input-bar');
            return { 
                exists: true, 
                text: ed.innerText, 
                htmlLen: ed.innerHTML.length,
                color: window.getComputedStyle(ed).color,
                barDisplay: bar ? window.getComputedStyle(bar).display : 'no-bar',
                barInDOM: bar ? bar.isConnected : false,
            };
        }""")
        log(f'生成中输入框: text="{editor_text2.get("text", "N/A")}" color={editor_text2.get("color")} barDisplay={editor_text2.get("barDisplay")} barInDOM={editor_text2.get("barInDOM")}')
        
        # anchor 检查
        anchor_check = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('.pea-node-editor-anchor');
            return Array.from(anchors).map(a => ({
                id: a.getAttribute('data-pea-anchor'),
                connected: a.isConnected,
                parentTag: a.parentElement?.tagName,
                parentDisplay: a.parentElement ? window.getComputedStyle(a.parentElement).display : 'N/A',
            }));
        }""")
        log(f'Anchor 元素: {json.dumps(anchor_check)}')
        
        # 控制条颜色检查
        ctrl_colors = await page.evaluate("""() => {
            const pill = document.querySelector('.pea-canvas-controls-pill');
            if (!pill) return { exists: false };
            const cs = window.getComputedStyle(pill);
            const btns = pill.querySelectorAll('.pea-canvas-controls-btn');
            const btnColors = Array.from(btns).slice(0, 3).map(b => ({
                color: window.getComputedStyle(b).color,
                bg: window.getComputedStyle(b).backgroundColor,
            }));
            return {
                exists: true,
                pillBg: cs.backgroundColor,
                pillColor: cs.color,
                btnColors,
            };
        }""")
        log(f'控制条: pillBg={ctrl_colors.get("pillBg")} pillColor={ctrl_colors.get("pillColor")}')
        for i, bc in enumerate(ctrl_colors.get('btnColors', [])):
            log(f'  按钮{i}: color={bc["color"]} bg={bc["bg"]}')
        
        await browser.close()
        log('\n=== 探测完成 ===')

asyncio.run(main())
