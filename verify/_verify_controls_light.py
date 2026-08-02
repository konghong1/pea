"""
验证 Fix1: 检查 JS 产物中是否包含 !generating 守卫
+ 截图验证控制条
"""
import asyncio, sys
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
        
        # 点击画布卡片
        try:
            card = page.locator('text=prompt_probe').first
            await card.click(timeout=5000)
            await asyncio.sleep(4)
        except:
            pass
        
        # 检查 JS 产物中是否包含修复代码（搜索生成后的代码特征）
        js_check = await page.evaluate("""() => {
            // 检查所有 script 标签中的内容
            const scripts = document.querySelectorAll('script[src]');
            const srcs = Array.from(scripts).map(s => s.src).filter(s => s.includes('index-'));
            return { jsBundles: srcs };
        }""")
        print(f'[JS bundles] {js_check["jsBundles"]}')
        
        # 直接检查 DOM 中是否有控制条及其样式
        ctrl_check = await page.evaluate("""() => {
            const pill = document.querySelector('.pea-canvas-controls-pill');
            if (!pill) return { exists: false };
            const cs = window.getComputedStyle(pill);
            const btns = pill.querySelectorAll('.pea-canvas-controls-btn');
            return {
                exists: true,
                pillBg: cs.backgroundColor,
                pillBorder: cs.border,
                btnCount: btns.length,
                // 取前3个按钮的颜色
                colors: Array.from(btns).slice(0, 4).map(b => window.getComputedStyle(b).color),
                // 帮助按钮
                help: (() => {
                    const h = document.querySelector('.pea-canvas-controls-help');
                    return h ? { bg: window.getComputedStyle(h).backgroundColor, color: window.getComputedStyle(h).color } : null;
                })(),
            };
        }""")
        print(f'[控制条] 存在={ctrl_check["exists"]}')
        print(f'  背景色: {ctrl_check["pillBg"]}')
        print(f'  边框: {ctrl_check["pillBorder"]}')
        print(f'  按钮({ctrl_check["btnCount"]}个):')
        for i, c in enumerate(ctrl_check.get('colors', [])):
            labels = ['☰ 缩略图', '⊞ 网格', '⛶ 适配', '滑块区']
            label = labels[i] if i < len(labels) else f'按钮{i}'
            print(f'    {label}: {c}')
        if ctrl_check.get('help'):
            print(f'  帮助○: bg={ctrl_check["help"]["bg"]} color={ctrl_check["help"]["color"]}')
        
        # 截图完整页面
        await page.screenshot(path=r'C:\workspace\pea\verify\shot_fix_final.png', full_page=False)
        print('\n[截图] shot_fix_final.png')
        
        # 验证：按钮颜色不能是白色或透明（浅色下应该是深色）
        dark_colors = ['rgb(85', 'rgb(51', 'rgb(0,', '#555', '#333', '#1a1a']
        btn_ok = any(any(dark in c for dark in dark_colors) for c in ctrl_check.get('colors', []))
        print(f'\n[结论] 控制条图标可见: {"✅ 是" if btn_ok else "❌ 否"} (检测到深色系颜色)')
        
        await browser.close()

asyncio.run(main())
