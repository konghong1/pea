"""Minimal debug: check what's on the page"""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        await page.add_init_script("localStorage.setItem('__peaDevHooks', '1');")
        
        # Capture console errors
        errors = []
        page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        
        await page.goto('http://localhost:8088', wait_until='networkidle', timeout=20000)
        await asyncio.sleep(1)
        await page.fill('input[placeholder*="you@"]', 'v3test@test.com')
        await page.fill('input[placeholder*="至少"]', 'Test123456')
        await page.press('input[placeholder*="至少"]', 'Enter')
        await asyncio.sleep(3)
        
        cid = await page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {
                method: 'POST',
                headers: {'Content-Type': 'application/json',
                          ...(token ? {Authorization: 'Bearer ' + token} : {})},
                body: JSON.stringify({title: 'minimal_debug', scope: 'personal'})
            });
            return (await r.json()).id;
        }""")
        
        await page.evaluate("""async (cid) => {
            let attempts = 0;
            while (typeof window.__canvas === 'undefined' && attempts < 30) {
                await new Promise(r => setTimeout(r, 500)); attempts++;
            }
            await window.__canvas.getState().openCanvas(cid);
            const ui = window.__ui;
            if (ui?.getState?.setActive) ui.getState().setActive('canvas');
        }""", cid)
        await asyncio.sleep(5)
        
        # Full page state dump
        state = await page.evaluate("""() => {
            const st = window.__canvas?.getState();
            return {
                url: location.href,
                bodyHTML: document.body?.innerHTML?.substring(0, 500),
                hasCanvas: !!window.__canvas,
                hasUi: !!window.__ui,
                canvasState: st ? {
                    canvasId: st.canvasId,
                    title: st.title,
                    nodesCount: st.nodes?.length,
                    edgesCount: st.edges?.length,
                    selectedId: st.selectedId,
                    nodes: st.nodes?.map(n => ({ id: n.id, type: n.type, selected: n.selected })),
                } : null,
                uiState: window.__ui?.getState ? {
                    active: window.__ui.getState().active,
                } : null,
                reactFlowEl: !!document.querySelector('.react-flow'),
                canvasEl: !!document.querySelector('.canvas-editor'),
                allClasses: Array.from(document.querySelectorAll('[class]')).slice(0, 20).map(e => e.className),
            };
        }""")
        print(json.dumps(state, indent=2, ensure_ascii=False))
        
        if errors:
            print(f'\nConsole errors ({len(errors)}):')
            for e in errors[:5]:
                print(f'  - {e[:200]}')
        
        await page.screenshot(path='verify/shot_minimal_debug.png')
        await browser.close()

asyncio.run(main())
