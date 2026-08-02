"""验证 v2 补充：进入画布编辑器验证输入框 + 芯片"""
import asyncio, json, urllib.request, time
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"
OUT  = "verify"
EMAIL = "v2c_20260802170200@pea.ai"  # 复用已注册账号
PW = "TestPass123!"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        print("Loading & logging in...")
        await page.goto(BASE + "/", wait_until="networkidle", timeout=25000)
        await page.wait_for_timeout(2000)

        # 登录
        email_input = await page.query_selector("input[type='text'], input[name='email'], input[placeholder*='@']")
        pwd_input = await page.query_selector("input[type='password']")
        submit = await page.query_selector("button[type='submit']")
        if email_input and pwd_input:
            await email_input.type(EMAIL, delay=20)
            await pwd_input.type(PW, delay=20)
            if submit:
                await submit.click()
                await page.wait_for_timeout(5000)

        # 点击 "新建项目" 进入画布
        print("Looking for new project button...")
        new_btn = await page.query_selector("button:has-text('新建项目'), a:has-text('新建项目')")
        if new_btn:
            await new_btn.click()
            print("  Clicked 新建项目")
            await page.wait_for_timeout(5000)
        
        # 也尝试点击 + 按钮
        plus_btn = await page.query_selector("button:has-text('+ 新建项目'), [class*='new']:has-text('+')")
        if plus_btn:
            await plus_btn.click()
            await page.wait_for_timeout(5000)

        # 检查是否有画布环境
        info = await page.evaluate("""() => {
            return {
                url: location.href,
                hasCanvas: !!window.__canvas,
                chip: !!document.querySelector('.pea-canvas-tapies'),
                inputBar: !!document.querySelector('.node-input-bar'),
                refBar: !!document.querySelector('.node-ref-bar'),
                icons: document.querySelectorAll('.pea-balance-gem').length
            };
        }""")
        print(f"State: {json.dumps(info, ensure_ascii=False)}")

        # 截图当前状态
        await page.screenshot(path=f"{OUT}/shot_v2_canvas_light.png")
        print("[OK] canvas_light")

        # 如果有芯片和输入栏，分别截图
        for sel, name in [(".pea-canvas-tapies", "chip"), 
                           (".node-input-bar", "inputbar"),
                           (".node-ref-bar", "refbar")]:
            el = await page.query_selector(sel)
            if el:
                await el.screenshot(path=f"{OUT}/shot_v2_canvas_light_{name}.png")
                print(f"[OK] canvas_light_{name}")

        # 切换深色
        await page.evaluate("""() => { document.documentElement.classList.add('dark'); }""")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{OUT}/shot_v2_canvas_dark.png")
        print("[OK] canvas_dark")

        for sel, name in [(".pea-canvas-tapies", "chip"), (".node-input-bar", "inputbar")]:
            el = await page.query_selector(sel)
            if el:
                await el.screenshot(path=f"{OUT}/shot_v2_canvas_dark_{name}.png")
                print(f"[OK] canvas_dark_{name}")

        # 探针：所有图标都是圆形
        probe = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.pea-balance-gem')).map(function(s,i){
                return {i:i, circles:s.querySelectorAll('circle').length, 
                       hasHex: Array.from(s.querySelectorAll('path')).some(function(p){
                           var d=p.getAttribute('d')||'';
                           return d.includes('Z') && (d.match(/L/g)||[]).length>=5;
                       })};
            });
        }""")
        print(f"\nIcons: {len(probe)}")
        for ic in probe:
            assert ic['circles'] > 0, f"[{ic['i']}] No circles!"
            assert not ic['hasHex'], f"[{ic['i']}] Has hexagon!"
            print(f"  [{ic['i']}] PASS - {ic['circles']} circles, round shape")

        # 输入框背景色检查
        bg = await page.evaluate("""() => {
            var b = document.querySelector('.node-input-bar');
            if (!b) return null;
            var s = window.getComputedStyle(b);
            return {bg: s.backgroundColor, border: s.borderColor};
        }""")
        if bg:
            print(f"\nInput bar: bg={bg['bg']}, border={bg['border']}")

        await browser.close()
    print("\n✅ Canvas verification done!")

if __name__ == "__main__":
    asyncio.run(main())
