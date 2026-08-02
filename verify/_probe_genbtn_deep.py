"""
深度探测：生成中点击按钮时 submit 是否运行、卡在哪
"""
import asyncio
import uuid
from playwright.async_api import async_playwright
from pathlib import Path

BASE = "http://localhost:8088"

async def main():
    email = f"deep_{uuid.uuid4().hex[:8]}@pea.ai"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        page.on('console', lambda m: print(f'[console.{m.type}] {m.text}'))
        page.on('pageerror', lambda e: print(f'[pageerror] {e}'))
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
            await browser.close(); return

        cid = await page.evaluate("""async () => {
            const t = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {method:'POST',
                headers:{'Content-Type':'application/json', ...(t?{Authorization:`Bearer ${t}`}:{})},
                body: JSON.stringify({name:'deep'})});
            const d = await r.json();
            return d.id || d.canvas?.id;
        }""")
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(800)

        await page.evaluate("""async (cid) => {
            const store = window.__canvas;
            if (store) await store.getState().openCanvas(cid);
            store.setState({ nodes:[{
                id:'nImg', type:'pea', position:{x:420,y:240},
                data:{ kind:'image', label:'Image',
                       prompt:'猫咪', generating:true, error:undefined,
                       resultUrl:undefined, resultUrls:undefined, lastJobId:'job_x' }
            }], edges:[], version:1, dirty:true });
            if (store.getState().select) store.getState().select('nImg');
            const ui = window.__ui; if (ui) ui.getState().setActive('canvas');
        }""", cid)
        await page.wait_for_timeout(1500)

        # 检查 React 内部状态：selectedNode 的 kind / genType 对应
        info = await page.evaluate("""() => {
            const store = window.__canvas;
            const s = store.getState();
            const sel = s.selectedNodeId;
            const n = s.nodes.find(x=>x.id==='nImg');
            return { selectedNodeId: sel, nodeKind: n?.data.kind, nodeGenerating: !!n?.data.generating,
                     nodesCount: s.nodes.length };
        }""")
        print(f'Store 状态: {info}')

        # 直接在按钮上派发真实 click，并监听是否触发任何 toast / 状态变化
        before = await page.evaluate("""() => {
            const n = window.__canvas.getState().nodes.find(x=>x.id==='nImg');
            return { generating: !!n.data.generating, lastJobId: n.data.lastJobId, resultUrl: n.data.resultUrl };
        }""")
        print(f'\n点击前: {before}')

        # 用 page.click 真实点击
        btn = page.locator('.pe-launcher').first
        print(f'按钮可见: {await btn.is_visible()}, 可点击: {await btn.is_enabled()}')
        try:
            await btn.click(timeout=5000, force=True)
            print('点击执行完成（未抛异常）')
        except Exception as e:
            print(f'点击抛异常: {type(e).__name__}: {e}')

        await page.wait_for_timeout(1500)
        after = await page.evaluate("""() => {
            const n = window.__canvas.getState().nodes.find(x=>x.id==='nImg');
            return { generating: !!n.data.generating, lastJobId: n.data.lastJobId, resultUrl: n.data.resultUrl,
                     error: n.data.error };
        }""")
        print(f'点击后: {after}')
        print(f'\n=== 结论 ===')
        print(f'状态变化: {"有" if before!=after else "无（submit 未生效或被吞）"}')
        await browser.close()

asyncio.run(main())
