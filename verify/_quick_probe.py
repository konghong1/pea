"""
快速探测：检查页面状态和可用全局变量
"""
import asyncio, sys, json
sys.path.insert(0, r'C:\workspace\pea')
from playwright.async_api import async_playwright

URL = 'http://localhost:8088'
EMAIL = 'v3test@test.com'
PWD = 'Test123456'

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
        
        # 检查当前 URL
        cur_url = page.url
        print(f'[URL] {cur_url}')
        
        # 截图看当前页面
        await page.screenshot(path=r'C:\workspace\pea\verify\shot_probe_current.png', full_page=False)
        
        # 检查全局变量
        globals_check = await page.evaluate("""() => {
            return {
                __canvas: typeof window.__canvas,
                __ui: typeof window.__ui,
                __store: typeof window.__store,
                keys: Object.keys(window).filter(k => k.startsWith('__')).slice(0, 10),
            };
        }""")
        print(f'[GLOBALS] {json.dumps(globals_check)}')
        
        # 尝试点击一个项目/画布进入编辑器
        # 先看看页面上有什么可点击的
        html = await page.content()
        print(f'[HTML length] {len(html)}')
        
        await browser.close()

asyncio.run(main())
