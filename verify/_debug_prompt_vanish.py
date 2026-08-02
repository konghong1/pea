"""
调试 v12：精确模拟用户场景
- 视频节点 + 有上传(fileKey) + 输入提示词 + 点击生成
"""
import asyncio, sys, json
from playwright.async_api import async_playwright

URL = 'http://localhost:8088'
EMAIL = 'v3test@test.com'
PWD = 'Test123456'

def log(msg): print(f'[DEBUG] {msg}')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        await page.add_init_script("localStorage.setItem('__peaDevHooks', '1');")
        
        await page.goto(URL, wait_until='networkidle', timeout=20000)
        await asyncio.sleep(1)
        await page.fill('input[placeholder*="you@"]', EMAIL)
        await page.fill('input[placeholder*="至少"]', PWD)
        await page.press('input[placeholder*="至少"]', 'Enter')
        await asyncio.sleep(3)
        
        cid = await page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {
                method: 'POST',
                headers: {'Content-Type': 'application/json',
                          ...(token ? {Authorization: 'Bearer ' + token} : {})},
                body: JSON.stringify({title: 'vanish_v12', scope: 'personal'})
            });
            return (await r.json()).id;
        }""")
        
        await page.evaluate("""
            async (cid) => {
                let attempts = 0;
                while (typeof window.__canvas === 'undefined' && attempts < 30) {
                    await new Promise(r => setTimeout(r, 500)); attempts++;
                }
                await window.__canvas.getState().openCanvas(cid);
                const ui = window.__ui;
                if (ui && ui.getState && ui.getState().setActive) ui.getState().setActive('canvas');
            }
        """, cid)
        await asyncio.sleep(5)
        
        # === Phase 1: 注入无 fileKey 节点，输入文字 ===
        log('=== Phase 1: 无 fileKey，正常输入 ===')
        await page.evaluate("""
            () => {
                window.__canvas.setState({
                    nodes: [{
                        id: 'nVid', type: 'pea', position: { x: 400, y: 250 },
                        data: { kind: 'video', label: 'Video', prompt: '', generating: false,
                                resultUrl: undefined, resultUrls: undefined, meta: {} }
                    }],
                    edges: [], version: 1, dirty: true
                });
                const st = window.__canvas.getState();
                if (st.select) st.select('nVid');
            }
        """)
        await asyncio.sleep(2)
        
        editor = page.locator('.node-prompt-editor').first
        assert await editor.count() > 0, 'editor should exist phase1'
        
        await editor.click()
        await asyncio.sleep(0.3)
        await editor.type('一只可爱的猫咪在草地上奔跑', delay=15)
        await asyncio.sleep(0.5)
        
        c1 = await editor.inner_text()
        log(f'Phase 1 输入后: "{c1}"')
        
        # === Phase 2: 添加 fileKey（模拟用户上传了图片）===
        log('=== Phase 2: 添加 fileKey ===')
        await page.evaluate("""
            () => {
                const st = window.__canvas.getState();
                // 添加 fileKey 但保持其他不变
                const node = st.nodes[0];
                st.updateNodeData('nVid', {
                    fileKey: 'user_uploaded_image_123.jpg',
                });
            }
        """)
        await asyncio.sleep(0.5)
        
        c2 = await editor.inner_text()
        log(f'Phase 2 添加fileKey后: "{c2}"')
        
        # 检查编辑器是否还在
        editor_count = await editor.count()
        log(f'编辑器元素数: {editor_count}')
        
        if editor_count == 0:
            log('!!! 编辑器消失了（isUploadedMedia 触发） !!!')
            # 这就是问题！添加 fileKey 后 isUploadedMedia 变 true → 编辑器卸载
            await page.screenshot(path='verify/shot_v12_filekey_hide.png')
            
            # 现在模拟生成开始
            log('=== Phase 3: 设置 generating=true ===')
            await page.evaluate("""
                () => {
                    const st = window.__canvas.getState();
                    st.updateNodeData('nVid', {
                        generating: true,
                        resultUrl: undefined,
                        resultUrls: undefined,
                        lastJobId: 'job_001',
                    });
                }
            """)
            await asyncio.sleep(1)
            
            # 检查编辑器是否恢复
            editor3 = page.locator('.node-prompt-editor').first
            count3 = await editor3.count()
            log(f'Phase 3 generating后编辑器数: {count3}')
            
            if count3 > 0:
                c3 = await editor3.inner_text()
                log(f'Phase 3 编辑器内容: "{c3}"')
            else:
                log('Phase 3 编辑器仍未出现!')
                
            await page.screenshot(path='verify/shot_v12_gen_phase.png')
            await browser.close()
            return
        
        # 如果编辑器没消失，继续测试生成流程
        log('=== Phase 3: 模拟生成（设置 generating=true）===')
        await page.evaluate("""
            () => {
                const st = window.__canvas.getState();
                const node = st.nodes[0];
                const html = '<p>一只可爱的猫咪在草地上奔跑</p>';
                st.updateNodeData('nVid', {
                    prompt: '一只可爱的猫咪在草地上奔跑',
                    meta: Object.assign({}, node.data.meta || {}, { editorText: html }),
                });
                st.updateNodeData('nVid', {
                    generating: true, error: undefined,
                    resultUrl: undefined, resultUrls: undefined,
                    resultIndex: 0, savedToLibrary: false,
                    lastJobId: 'job_sim_001',
                });
            }
        """)
        await asyncio.sleep(1.5)
        
        c3 = await editor.inner_text()
        log(f'Phase 3 生成后: "{c3}"')
        await page.screenshot(path='verify/shot_v12_result.png')
        
        if c3.strip() and '猫咪' in c3:
            log('PROMPT PRESERVED (with fileKey)')
        else:
            log('PROMPT VANISHED (with fileKey)!')
        
        await browser.close()

asyncio.run(main())
