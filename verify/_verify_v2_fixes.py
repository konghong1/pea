"""验证 v2：圆形光球图标 + 输入框浅色修复（真实登录）"""
import asyncio, json, urllib.request, time
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"
OUT  = "verify"

STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"v2c_{STAMP}@pea.ai"
PW = "TestPass123!"

async def main():
    # 预注册
    print("Registering...")
    try:
        urllib.request.urlopen(urllib.request.Request(
            BASE + "/api/auth/register", method="POST",
            data=json.dumps({"email": EMAIL, "password": PW}).encode(),
            headers={"Content-Type": "application/json"}), timeout=10)
        print(f"  OK: {EMAIL}")
    except Exception as e:
        print(f"  {e}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        print("Loading app...")
        await page.goto(BASE + "/", wait_until="networkidle", timeout=25000)
        await page.wait_for_timeout(2000)

        # 填写登录表单
        print("Logging in...")
        email_input = await page.query_selector("input[type='text'], input[name='email'], input[placeholder*='@']")
        pwd_input = await page.query_selector("input[type='password']")
        submit = await page.query_selector("button[type='submit']")

        if email_input and pwd_input:
            await email_input.click()
            await email_input.type(EMAIL, delay=30)
            await pwd_input.click()
            await pwd_input.type(PW, delay=30)
            if submit:
                await submit.click()
                print("  Form submitted")
                # 等待导航完成
                try:
                    await page.wait_for_url("**/canvas**", timeout=10000)
                except:
                    pass
                await page.wait_for_timeout(5000)

        # 检查是否到了画布页
        url = page.url
        print(f"  URL: {url}")
        
        # 尝试点击错误恢复按钮（如果有）
        retry_btn = await page.query_selector("button:has-text('刷新'), button:has-text('返回'), button:has-text('重试')")
        if retry_btn:
            print("  Clicking recovery button...")
            await retry_btn.click()
            await page.wait_for_timeout(5000)

        # 再试一次点击"返回工作空间"
        workspace_btn = await page.query_selector("button:has-text('工作空间'), button:has-text('workspace')")
        if workspace_btn:
            await workspace_btn.click()
            await page.wait_for_timeout(3000)

        # 截图当前状态
        await page.screenshot(path=f"{OUT}/shot_v2_state.png")
        
        # 探测所有可见元素
        info = await page.evaluate("""() => {
            return {
                url: location.href,
                hasCanvas: !!window.__canvas,
                hasUi: !!window.__ui,
                topnav: !!document.querySelector('.pea-topnav, header'),
                balanceBtn: !!document.querySelector('.pea-topnav-balance'),
                canvasChip: !!document.querySelector('.pea-canvas-tapies'),
                inputBar: !!document.querySelector('.node-input-bar'),
                bodyText: document.body?.innerText?.substring(0, 300) || ''
            };
        }""")
        print(f"\nState: {json.dumps(info, ensure_ascii=False)}")

        # 如果有画布环境，设置节点
        if info.get('hasCanvas') and info.get('hasUi'):
            print("\nSetting up canvas...")
            tok = json.loads(urllib.request.urlopen(urllib.request.Request(
                BASE + "/api/auth/login", method="POST",
                data=json.dumps({"email": EMAIL, "password": PW}).encode(),
                headers={"Content-Type": "application/json"}), timeout=10).read().decode())["token"]
            
            cvs = json.loads(urllib.request.urlopen(urllib.request.Request(
                BASE + "/api/canvases", method="POST",
                data=json.dumps({"title": "v2", "type": "personal"}).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + tok}), timeout=10).read().decode())
            
            cid, cver = str(cvs.get('id')), str(cvs.get('version'))
            js = ("var u=window.__ui.getState();var c=window.__canvas.getState();"
                  "u.setActive('canvas');c.setCanvasMeta("+cid+","+cver+",'v2');"
                  "c.loadGraph([{id:'n1',type:'pea',position:{x:400,y:300},data:{kind:'image',label:'Img'}}],[],"+cver+");"
                  "c.setSelection(['n1']);")
            await page.evaluate(js)
            await page.wait_for_timeout(2500)

        # ====== 截图 ======
        for theme, cls in [("light", ""), ("dark", "dark")]:
            print(f"\n=== {theme.upper()} ===")
            if cls:
                await page.evaluate("""() => { document.documentElement.classList.add('dark'); }""")
            else:
                await page.evaluate("""() => { document.documentElement.classList.remove('dark'); }""")
            await page.wait_for_timeout(1200)
            
            await page.screenshot(path=f"{OUT}/shot_v2_{theme}_full.png")
            print(f"[OK] {theme}_full")
            
            for sel, name in [(".pea-topnav-balance", "balance"), (".pea-canvas-tapies", "chip"),
                               (".node-input-bar", "inputbar"), (".node-ref-bar", "refbar")]:
                el = await page.query_selector(sel)
                if el:
                    await el.screenshot(path=f"{OUT}/shot_v2_{theme}_{name}.png")
                    print(f"[OK] {theme}_{name}")

        # 探针
        print("\n=== PROBE ===")
        probe = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.pea-balance-gem')).map(function(s,i){
                return {i:i, circles:s.querySelectorAll('circle').length, paths:s.querySelectorAll('path').length};
            });
        }""")
        print(f"Icons: {len(probe)}")
        for ic in probe:
            ok = ic['circles'] > 0
            print(f"  [{ic['i']}] circles={ic['circles']} {'PASS' if ok else 'FAIL'}")

        await browser.close()
    print("\n✅ Done!")

if __name__ == "__main__":
    asyncio.run(main())
