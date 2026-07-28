import asyncio
import uuid
from playwright.async_api import async_playwright
from pathlib import Path

BASE = "http://localhost:8088"
OUT = Path(__file__).parent / "shots" / "image_failure" / "generating-state-redesign.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

async def main():
    email = f"gen_{uuid.uuid4().hex[:8]}@pea.ai"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        await page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

        # register + login
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
        await page.wait_for_selector('text=新建项目', timeout=15000)

        # create canvas via API
        cid = await page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/canvases', {
                method: 'POST',
                headers: {'Content-Type': 'application/json',
                          ...(token ? {Authorization: `Bearer ${token}`} : {})},
                body: JSON.stringify({title: 'generating_state_test', scope: 'personal'})
            });
            return (await r.json()).id;
        }""")

        # switch to canvas editor and inject generating node
        await page.goto(BASE, wait_until="domcontentloaded")
        await page.wait_for_timeout(800)
        await page.evaluate("""async (cid) => {
            const store = window.__canvas;
            await store.getState().openCanvas(cid);
            store.setState({
                nodes: [{
                    id: 'nImg',
                    type: 'pea',
                    position: {x: 420, y: 240},
                    data: {
                        kind: 'image',
                        label: 'Image',
                        prompt: '科技感城市夜景',
                        generating: true,
                        error: undefined,
                        resultUrl: undefined,
                        resultUrls: undefined
                    }
                }],
                edges: [],
                version: 1,
                dirty: true,
            });
            store.getState().select('nImg');
            window.__ui.getState().setActive('canvas');
        }""", cid)
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(OUT), full_page=False)
        print(f"Screenshot saved: {OUT}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
