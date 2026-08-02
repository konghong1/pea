"""Quick anchor debug"""
import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        await page.add_init_script("localStorage.setItem('__peaDevHooks', '1');")
        
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
                body: JSON.stringify({title: 'debug_anchor', scope: 'personal'})
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
        
        # Inject node with fileKey
        await page.evaluate("""() => {
            window.__canvas.setState({
                nodes: [{
                    id: 'nVid', type: 'pea', position: { x: 400, y: 250 },
                    data: { kind: 'video', label: 'Video', prompt: '',
                            generating: false, fileKey: 'test.jpg',
                            resultUrl: undefined, resultUrls: undefined, meta: {} }
                }],
                edges: [], version: 1, dirty: true
            });
            window.__canvas.getState().select?.('nVid');
        }""")
        await asyncio.sleep(2)
        
        info = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('[data-pea-anchor]');
            const anchorInfo = [];
            anchors.forEach(a => anchorInfo.push({ attr: a.getAttribute('data-pea-anchor'), cls: a.className }));
            
            const st = window.__canvas.getState();
            return {
                anchorCount: anchors.length,
                anchors: anchorInfo,
                selectedId: st.selectedId,
                selectedIds: st.selectedIds,
                nodes: st.nodes.map(n => ({ id: n.id, selected: n.selected })),
                editorCount: document.querySelectorAll('.node-prompt-editor').length,
                inputBarCount: document.querySelectorAll('.node-input-bar').length,
                peaNodeCount: document.querySelectorAll('.pea-node').length,
            };
        }""")
        print(json.dumps(info, indent=2))
        await browser.close()

asyncio.run(main())
