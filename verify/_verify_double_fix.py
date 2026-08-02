"""
验证两个修复：
1. 生成中提示词不消失（isUploadedMedia 守卫增加 !data.generating 条件）
2. 浅色下画布控制条图标可见
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
        
        # 点击第一个画布进入编辑器
        log('点击画布卡片...')
        try:
            card = page.locator('text=prompt_probe').first
            await card.click(timeout=5000)
            await asyncio.sleep(4)
        except Exception as e:
            log(f'点击失败，尝试新建: {e}')
            # 尝试点"新建项目"
            new_btn = page.locator('text=新建项目').first
            if await new_btn.count() > 0:
                await new_btn.click()
                await asyncio.sleep(3)
        
        cur_url = page.url
        log(f'URL: {cur_url}')
        
        # 等待 store 可用
        store_ready = False
        for attempt in range(10):
            store_ready = await page.evaluate("""() => typeof window.__canvas !== 'undefined'""")
            if store_ready:
                break
            await asyncio.sleep(1)
        
        if not store_ready:
            log('Store 未就绪，截图后退出')
            await page.screenshot(path=r'C:\workspace\pea\verify\shot_fix_verify_nostore.png', full_page=False)
            await browser.close()
            return
        
        log('Store 就绪 ✓')
        
        # 注入视频节点（带 fileKey 模拟上传过 + 非生成状态）
        log('注入视频节点...')
        await page.evaluate("""() => {
            const store = window.__canvas;
            const nid = 'vid_test';
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
                        fileKey: 'test-upload-key',   // 模拟有上传文件
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
        
        # === 生成前检查 ===
        before = await page.evaluate("""() => {
            const ed = document.querySelector('.node-prompt-editor');
            const bar = document.querySelector('.node-input-bar');
            return {
                editorExists: !!ed,
                editorText: ed ? ed.innerText : 'N/A',
                barExists: !!bar,
                barDisplay: bar ? window.getComputedStyle(bar).display : 'N/A',
            };
        }""")
        log(f'生成前: editor={before["editorText"][:40]} bar={before["barDisplay"]}')
        
        # 切换到 generating（模拟点击生成）
        log('>>> 切换 generating=true ...')
        await page.evaluate("""() => {
            const store = window.__canvas;
            store.getState().updateNodeData('vid_test', { 
                generating: true,
                resultUrl: undefined, 
                resultUrls: undefined 
            });
        }""")
        await asyncio.sleep(2)
        
        # === 生成中检查（关键验证）===
        during = await page.evaluate("""() => {
            const ed = document.querySelector('.node-prompt-editor');
            const bar = document.querySelector('.node-input-bar');
            const anchor = document.querySelector('.pea-node-editor-anchor[data-pea-anchor="vid_test"]');
            return {
                editorExists: !!ed,
                editorText: ed ? ed.innerText : 'N/A',
                editorColor: ed ? window.getComputedStyle(ed).color : 'N/A',
                barExists: !!bar,
                barDisplay: bar ? window.getComputedStyle(bar).display : 'N/A',
                barInDOM: bar ? bar.isConnected : false,
                anchorExists: !!anchor,
                anchorConnected: anchor ? anchor.isConnected : false,
            };
        }""")
        log(f'生成中: editor="{during["editorText"][:40] if during["editorText"] else "N/A"}" bar={during["barDisplay"]} anchorOK={during["anchorConnected"]}')
        
        # 截图：生成中状态
        await page.screenshot(path=r'C:\workspace\pea\verify\shot_fix_prompt_gen.png', full_page=False)
        
        # === 控制条可见性检查 ===
        ctrl = await page.evaluate("""() => {
            const pill = document.querySelector('.pea-canvas-controls-pill');
            if (!pill) return { exists: false };
            const cs = window.getComputedStyle(pill);
            const btns = pill.querySelectorAll('.pea-canvas-controls-btn');
            const slider = pill.querySelector('input[type="range"]');
            const help = document.querySelector('.pea-canvas-controls-help');
            return {
                exists: true,
                pillBg: cs.backgroundColor,
                pillBorder: cs.borderColor,
                btnCount: btns.length,
                btnColors: Array.from(btns).slice(0, 3).map(b => ({
                    color: window.getComputedStyle(b).color,
                    visible: window.getComputedStyle(b).color !== 'rgba(0, 0, 0, 0)' && 
                             window.getComputedStyle(b).color !== 'rgb(255, 255, 255)',
                })),
                sliderBg: slider ? window.getComputedStyle(slider).backgroundColor : 'N/A',
                helpBg: help ? window.getComputedStyle(help).backgroundColor : 'N/A',
                helpColor: help ? window.getComputedStyle(help).color : 'N/A',
            };
        }""")
        log(f'控制条: pillBg={ctrl.get("pillBg")} btnCount={ctrl.get("btnCount")}')
        for i, bc in enumerate(ctrl.get('btnColors', [])):
            log(f'  按钮{i}: color={bc["color"]} visible={bc["visible"]}')
        log(f'  滑块: bg={ctrl.get("sliderBg")}')
        log(f'  帮助按钮: bg={ctrl.get("helpBg")} color={ctrl.get("helpColor")}')
        
        # 截图：控制条区域（裁剪底部）
        await page.screenshot(path=r'C:\workspace\pea\verify\shot_fix_controls_light.png', full_page=False)
        
        # === 结果判定 ===
        results = {}
        
        # Fix 1: 提示词不消失
        results['fix1_prompt_visible'] = (
            during['editorExists'] and 
            len(during.get('editorText', '')) > 5 and
            during['barInDOM']
        )
        results['fix1_bar_visible'] = during['barExists'] and during['barInDOM']
        
        # Fix 2: 控制条可见
        all_btns_visible = all(bc.get('visible') for bc in ctrl.get('btnColors', []))
        results['fix2_buttons_visible'] = ctrl.get('exists') and all_btns_visible
        results['fix2_slider_visible'] = ctrl.get('sliderBg', '') != 'rgba(0, 0, 0, 0)'
        results['fix2_help_visible'] = ctrl.get('helpColor', '') not in ['rgba(0, 0, 0, 0)', 'rgb(255, 255, 255)']
        
        log('\n=== 验证结果 ===')
        for k, v in results.items():
            status = '✅ PASS' if v else '❌ FAIL'
            log(f'  {k}: {status}')
        
        all_pass = all(results.values())
        log(f'\n总体: {"全部通过 ✅" if all_pass else "有失败项 ❌"}')
        
        await browser.close()
        return all_pass

asyncio.run(main())
