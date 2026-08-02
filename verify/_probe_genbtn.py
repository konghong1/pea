"""
探测：生成过程中生成按钮是否可点击，以及为什么不可点击
"""
import asyncio
import uuid
from playwright.async_api import async_playwright
from pathlib import Path

BASE = "http://localhost:8088"
OUT = Path(r'C:\workspace\pea\verify\shot_genbtn_probe.png')
OUT.parent.mkdir(parents=True, exist_ok=True)

async def main():
    email = f"genbtn_{uuid.uuid4().hex[:8]}@pea.ai"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        await page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

        print('注册/登录...')
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
            await page.screenshot(path=str(OUT)); await browser.close(); return

        # 创建画布
        cid = await page.evaluate("""async () => {
            const t = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {method:'POST',
                headers:{'Content-Type':'application/json', ...(t?{Authorization:`Bearer ${t}`}:{})},
                body: JSON.stringify({name:'genbtn_probe'})});
            const d = await r.json();
            return d.id || d.canvas?.id;
        }""")
        print(f'画布 ID: {cid}')

        # 注入一个已有 prompt 的图片节点（模拟用户已输入）
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(800)
        await page.evaluate("""async (cid) => {
            const store = window.__canvas;
            if (store) await store.getState().openCanvas(cid);
            store.setState({ nodes:[{
                id:'nImg', type:'pea', position:{x:420,y:240},
                data:{ kind:'image', label:'Image',
                       prompt:'一只可爱的猫咪',
                       generating:false, error:undefined,
                       resultUrl:undefined, resultUrls:undefined }
            }], edges:[], version:1, dirty:true });
            if (store.getState().select) store.getState().select('nImg');
            const ui = window.__ui; if (ui) ui.getState().setActive('canvas');
        }""", cid)
        await page.wait_for_timeout(1200)

        # 真实在编辑器里输入文字（让 canSend=true）
        editor = page.locator('.node-prompt-editor[contenteditable="true"]').first
        if await editor.count() == 0:
            editor = page.locator('[contenteditable="true"]').first
        if await editor.count() > 0:
            await editor.click()
            await editor.type('一只可爱的猫咪在阳光下打盹', delay=25)
            await page.wait_for_timeout(500)
            print('已在编辑器输入文字')
        else:
            print('未找到编辑器，无法输入')

        # 找到生成按钮
        btn = page.locator('.pe-launcher').first
        print(f'生成按钮存在: {await btn.count() > 0}')

        # 记录初始状态
        def btn_state():
            return page.evaluate("""() => {
                const b = document.querySelector('.pe-launcher');
                if (!b) return null;
                const cs = getComputedStyle(b);
                const rect = b.getBoundingClientRect();
                return {
                    cls: b.className,
                    disabled: b.getAttribute('disabled'),
                    onClick: b.getAttribute('onclick') ? 'has' : 'none',
                    pointerEvents: cs.pointerEvents,
                    cursor: cs.cursor,
                    hasDisabledClass: b.classList.contains('disabled'),
                    width: Math.round(rect.width), height: Math.round(rect.height),
                    visible: rect.width>0 && rect.height>0,
                    topMost: (() => {
                        const el = document.elementFromPoint(rect.x+rect.width/2, rect.y+rect.height/2);
                        return el ? (el.className?.toString().slice(0,60)) : 'null';
                    })()
                };
            }""")

        print('\n--- 初始状态（非生成中）---')
        s0 = await btn_state()
        print(s0)

        # 模拟点击生成 → 进入生成中
        await btn.click()
        # 立即（提交阶段）和稍后（生成中）分别探测
        await page.wait_for_timeout(300)
        print('\n--- 点击后 300ms（可能处于 submitting 阶段）---')
        s1 = await btn_state()
        print(s1)

        await page.wait_for_timeout(2500)
        print('\n--- 点击后 ~2.8s（应已进入生成中）---')
        s2 = await btn_state()
        print(s2)

        # 检查节点是否处于 generating
        gen_state = await page.evaluate("""() => {
            const store = window.__canvas;
            if (!store) return 'no-store';
            const ns = store.getState().nodes;
            const n = ns.find(x => x.id === 'nImg');
            return n ? { generating: !!n.data.generating, hasResult: !!n.data.resultUrl } : 'no-node';
        }""")
        print(f'\n节点生成状态: {gen_state}')

        # 尝试在生成中点击按钮（探测是否可点击）
        print('\n--- 尝试在生成中点击按钮 ---')
        try:
            # 用 JS 直接派发 click，看 submit 是否被触发
            before = await page.evaluate("""() => {
                const store = window.__canvas;
                const n = store.getState().nodes.find(x=>x.id==='nImg');
                return n ? n.data.lastJobId : null;
            }""")
            await btn.click(timeout=3000)
            await page.wait_for_timeout(1500)
            after = await page.evaluate("""() => {
                const store = window.__canvas;
                const n = store.getState().nodes.find(x=>x.id==='nImg');
                return n ? n.data.lastJobId : null;
            }""")
            print(f'点击前 lastJobId: {before}')
            print(f'点击后 lastJobId: {after}')
            print(f'结果: {"按钮有响应（重新触发生成）" if before != after else "按钮无响应（被禁用/吞掉）"}')
        except Exception as e:
            print(f'点击按钮异常（可能被禁用）: {type(e).__name__}')

        await page.screenshot(path=str(OUT), full_page=False)
        print(f'\n截图: {OUT}')
        await browser.close()

asyncio.run(main())
