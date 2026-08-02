"""
隔离测试：直接注入 generating:true 节点，检查生成按钮是否可点击
"""
import asyncio
import uuid
from playwright.async_api import async_playwright
from pathlib import Path

BASE = "http://localhost:8088"
OUT = Path(r'C:\workspace\pea\verify\shot_genbtn_iso.png')
OUT.parent.mkdir(parents=True, exist_ok=True)

async def main():
    email = f"iso_{uuid.uuid4().hex[:8]}@pea.ai"
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
                body: JSON.stringify({name:'iso_gen'})});
            const d = await r.json();
            return d.id || d.canvas?.id;
        }""")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(800)

        # 注入 generating:true 节点 + 编辑器里有内容（让 canSend=true）
        await page.evaluate("""async (cid) => {
            const store = window.__canvas;
            if (store) await store.getState().openCanvas(cid);
            store.setState({ nodes:[{
                id:'nImg', type:'pea', position:{x:420,y:240},
                data:{ kind:'image', label:'Image',
                       prompt:'一只可爱的猫咪',
                       generating:true, error:undefined,
                       resultUrl:undefined, resultUrls:undefined,
                       lastJobId:'job_test_123' }
            }], edges:[], version:1, dirty:true,
            selectedIds:['nImg'], selectedId:'nImg' });
            const ui = window.__ui; if (ui) ui.getState().setActive('canvas');
        }""", cid)
        await page.wait_for_timeout(1200)

        # 真实在编辑器里输入，确保 hasInput=true
        editor = page.locator('.node-prompt-editor[contenteditable="true"]').first
        if await editor.count() > 0:
            await editor.click()
            await editor.type('测试提示词', delay=20)
            await page.wait_for_timeout(400)

        def btn_state():
            return page.evaluate("""() => {
                const b = document.querySelector('.pe-launcher');
                if (!b) return null;
                const cs = getComputedStyle(b);
                const rect = b.getBoundingClientRect();
                const cx = rect.x+rect.width/2, cy = rect.y+rect.height/2;
                const topEl = document.elementFromPoint(cx, cy);
                return {
                    cls: b.className,
                    hasDisabledClass: b.classList.contains('disabled'),
                    pointerEvents: cs.pointerEvents,
                    cursor: cs.cursor,
                    computedCursor: cs.cursor,
                    visible: rect.width>0 && rect.height>0,
                    centerElClass: topEl ? topEl.className?.toString().slice(0,80) : 'null',
                    centerIsButtonOrChild: !!(topEl && (topEl.closest && topEl.closest('.pe-launcher'))),
                };
            }""")

        print('=== 节点处于 generating:true 时，按钮状态 ===')
        s = await btn_state()
        print(s)

        # 尝试点击，看 submit 是否触发（lastJobId 变化）
        gen_before = await page.evaluate("""() => {
            const n = window.__canvas.getState().nodes.find(x=>x.id==='nImg');
            return n ? { generating: !!n.data.generating, lastJobId: n.data.lastJobId } : null;
        }""")
        print(f'\n点击前节点: {gen_before}')

        try:
            await page.locator('.pe-launcher').first.click(timeout=3000)
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f'点击异常: {type(e).__name__}')

        gen_after = await page.evaluate("""() => {
            const n = window.__canvas.getState().nodes.find(x=>x.id==='nImg');
            return n ? { generating: !!n.data.generating, lastJobId: n.data.lastJobId } : null;
        }""")
        print(f'点击后节点: {gen_after}')
        print(f'\n结论: {"按钮可点击（submit 触发）" if gen_before!=gen_after else "按钮无响应（被禁用/吞掉点击）"}')

        await page.screenshot(path=str(OUT), full_page=False)
        await browser.close()

asyncio.run(main())
