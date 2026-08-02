"""
最终验证：生成中按钮(停止) + 非生成中按钮(正常生成) + 浅色主题
"""
import asyncio
import uuid
from playwright.async_api import async_playwright
from pathlib import Path

BASE = "http://localhost:8088"
OUT = Path(r'C:\workspace\pea\verify\shot_genbtn_stop.png')
OUT.parent.mkdir(parents=True, exist_ok=True)

async def main():
    email = f"final_{uuid.uuid4().hex[:8]}@pea.ai"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        await page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

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
        if not token:
            await page.screenshot(path=str(OUT)); await browser.close(); return

        cid = await page.evaluate("""async () => {
            const t = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {method:'POST',
                headers:{'Content-Type':'application/json', ...(t?{Authorization:`Bearer ${t}`}:{})},
                body: JSON.stringify({name:'final_stop'})});
            const d = await r.json();
            return d.id || d.canvas?.id;
        }""")

        # 浅色主题注入生成中节点并截图
        await page.emulate_media(color_scheme='light')
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(800)
        await page.evaluate("""async (cid) => {
            const store = window.__canvas;
            if (store) await store.getState().openCanvas(cid);
            store.setState({ nodes:[{
                id:'nImg', type:'pea', position:{x:420,y:240},
                data:{ kind:'image', label:'Image',
                       prompt:'一只可爱的猫咪', generating:true, error:undefined,
                       resultUrl:undefined, resultUrls:undefined, lastJobId:'job_x' }
            }], edges:[], version:1, dirty:true, selectedIds:['nImg'], selectedId:'nImg' });
            const ui = window.__ui; if (ui) ui.getState().setActive('canvas');
        }""", cid)
        await page.wait_for_timeout(1500)

        # 验证1：生成中按钮为停止态
        s1 = await page.evaluate("""() => {
            const b = document.querySelector('.pe-launcher');
            return { cls: b.className, cursor: getComputedStyle(b).cursor,
                     costText: b.querySelector('.pe-cost-num')?.textContent,
                     hasStopIcon: !!b.querySelector('.pe-stop-icon'),
                     onClick: b.getAttribute('onclick')?'attr':'react' };
        }""")
        print('生成中按钮状态:', s1)

        await page.screenshot(path=str(OUT), full_page=False)
        print(f'浅色主题截图: {OUT}')

        # 验证2：点击停止 → 生成态解除
        await page.locator('.pe-launcher').first.click()
        await page.wait_for_timeout(800)
        after = await page.evaluate("""() => {
            const n = window.__canvas.getState().nodes.find(x=>x.id==='nImg');
            const b = document.querySelector('.pe-launcher');
            return { generating: !!n.data.generating, btnCls: b.className,
                     costText: b.querySelector('.pe-cost-num')?.textContent };
        }""")
        print('点击停止后:', after)

        # 验证3：非生成中普通节点按钮应为正常生成态（无 is-stopping）
        await page.evaluate("""() => {
            const store = window.__canvas;
            store.setState({ nodes:[{
                id:'nImg2', type:'pea', position:{x:420,y:480},
                data:{ kind:'image', label:'Image', prompt:'测试',
                       generating:false, error:undefined,
                       resultUrl:undefined, resultUrls:undefined }
            }], selectedIds:['nImg2'], selectedId:'nImg2' });
        }""")
        await page.wait_for_timeout(800)
        s3 = await page.evaluate("""() => {
            const b = document.querySelector('.pe-launcher');
            return { cls: b.className, hasStopIcon: !!b.querySelector('.pe-stop-icon'),
                     costText: b.querySelector('.pe-cost-num')?.textContent };
        }""")
        print('非生成中按钮状态:', s3)

        # 总结
        print('\n===== 结果 =====')
        ok1 = 'is-stopping' in s1['cls'] and s1['hasStopIcon'] and s1['costText']=='停止'
        ok2 = after['generating']==False and 'is-stopping' not in after['btnCls']
        ok3 = 'is-stopping' not in s3['cls'] and not s3['hasStopIcon']
        print(f'1. 生成中→停止按钮: {"✅" if ok1 else "❌"} (cls={s1["cls"]}, icon={s1["hasStopIcon"]}, text={s1["costText"]})')
        print(f'2. 点击停止→解除:   {"✅" if ok2 else "❌"} (generating={after["generating"]})')
        print(f'3. 非生成中→正常:   {"✅" if ok3 else "❌"} (cls={s3["cls"]})')
        print(f'\n{"🎉 全部通过" if ok1 and ok2 and ok3 else "⚠️ 部分失败"}')
        await browser.close()

asyncio.run(main())
