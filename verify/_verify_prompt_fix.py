"""Final test: force canvas view + node creation + prompt preservation"""
import asyncio, json
from playwright.async_api import async_playwright

URL = 'http://localhost:8088'
EMAIL = 'v3test@test.com'
PWD = 'Test123456'

def log(msg): print(f'[TEST] {msg}')

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
                body: JSON.stringify({title: 'final_test', scope: 'personal'})
            });
            return (await r.json()).id;
        }""")
        
        # 进入画布：先 setActive 再 openCanvas
        log('切换到 canvas 视图...')
        nav = await page.evaluate("""async (cid) => {
            try {
                let attempts = 0;
                while ((typeof window.__canvas === 'undefined' || typeof window.__ui === 'undefined') && attempts < 30) {
                    await new Promise(r => setTimeout(r, 500)); attempts++;
                }
                
                // 先切到 canvas 视图
                window.__ui.setState({ active: 'canvas' });
                
                // 再打开画布
                await window.__canvas.getState().openCanvas(cid);
                
                return { ok: true };
            } catch(e) {
                return { error: e.message, stack: e.stack };
            }
        }""", cid)
        log(f'导航: {json.dumps(nav)}')
        await asyncio.sleep(5)
        
        # 确认视图状态
        ui_check = await page.evaluate("""() => ({
            active: window.__ui?.getState?.()?.active,
            hasReactFlow: !!document.querySelector('.react-flow'),
            hasCanvasEditor: !!document.querySelector('[class*="canvas-editor"]'),
            url: location.href,
        })""")
        log(f'视图状态: {json.dumps(ui_check)}')
        
        if ui_check.get('active') != 'canvas':
            log('仍然不是 canvas 视图，截图查看')
            await page.screenshot(path='verify/shot_not_canvas.png')
            await browser.close()
            return
        
        # 现在应该有 ReactFlow 了。双击创建节点
        log('双击画布创建节点...')
        rf = page.locator('.react-flow').first
        if await rf.count() > 0:
            await rf.dblclick(position={'x': 400, 'y': 250})
            await asyncio.sleep(2)
            
            # 检查节点是否创建
            node_info = await page.evaluate("""() => {
                const anchors = document.querySelectorAll('[data-pea-anchor]');
                const nodes = document.querySelectorAll('.pea-node');
                const editors = document.querySelectorAll('.node-prompt-editor');
                return {
                    anchorCount: anchors.length,
                    anchorAttrs: Array.from(anchors).map(a => a.getAttribute('data-pea-anchor')),
                    nodeCount: nodes.length,
                    nodeIds: Array.from(nodes).map(n => n.id),
                    editorCount: editors.length,
                    storeNodes: window.__canvas?.getState()?.nodes?.map(n => ({id:n.id, kind:n.data.kind})),
                };
            }""")
            log(f'节点信息: {json.dumps(node_info)}')
            
            if node_info['nodeCount'] > 0 and node_info['editorCount'] > 0:
                nid = node_info['nodeIds'][0]
                log(f'节点 {nid} 创建成功，编辑器已显示!')
                
                # 修改为视频+fileKey
                await page.evaluate("""(nid) => {
                    window.__canvas.getState().updateNodeData(nid, {
                        kind: 'video',
                        label: 'Video',
                        generating: false,
                        fileKey: 'user_upload.jpg',
                        resultUrl: undefined,
                        resultUrls: undefined,
                    });
                }""", nid)
                await asyncio.sleep(1)
                
                # 检查编辑器是否还在（关键测试！）
                editor = page.locator('.node-prompt-editor').first
                ec = await editor.count()
                log(f'修改为视频+fileKey后编辑器数: {ec}')
                
                if ec == 0:
                    log('FAIL: 编辑器被 isUploadedMedia 隐藏了（修复未生效？）')
                    await page.screenshot(path='verify/shot_filekey_hide.png')
                    await browser.close()
                    return
                
                log('PASS: 编辑器仍显示（isUploadedMedia 检查已移除）')
                
                # 输入提示词
                await editor.click()
                await asyncio.sleep(0.3)
                await editor.type('一只可爱的猫咪在草地上奔跑', delay=15)
                await asyncio.sleep(0.5)
                
                before = await editor.inner_text()
                log(f'输入后: "{before}"')
                
                # 模拟生成开始
                log('--- 模拟生成 ---')
                await page.evaluate("""(nid) => {
                    const st = window.__canvas.getState();
                    const node = st.nodes.find(n => n.id === nid);
                    const html = '<p>一只可爱的猫咪在草地上奔跑</p>';
                    
                    st.updateNodeData(nid, {
                        prompt: '一只可爱的猫咪在草地上奔跑',
                        meta: Object.assign({}, node.data.meta || {}, { editorText: html }),
                    });
                    st.updateNodeData(nid, {
                        generating: true,
                        lastJobId: 'job_final',
                    });
                }""", nid)
                await asyncio.sleep(1.5)
                
                after = await editor.inner_text()
                log(f'生成后: "{after}"')
                await page.screenshot(path='verify/shot_final_verified.png')
                
                if after.strip() and '猫咪' in after:
                    log('')
                    log('='*50)
                    log('✅✅✅ 全部通过！提示词在生成中保留了！')
                    log('='*50)
                else:
                    log('')
                    log('='*50)
                    log('❌❌❌ 提示词消失了！')
                    log('='*50)
            else:
                log(f'节点/编辑器未出现: {json.dumps(node_info)}')
                await page.screenshot(path='verify/shot_no_node.png')
        else:
            log('无 react-flow 容器')
            await page.screenshot(path='verify/shot_no_rf.png')
        
        await browser.close()

asyncio.run(main())
