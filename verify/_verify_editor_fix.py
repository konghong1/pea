"""Verify editor text visibility fix."""
import asyncio, json, time
from playwright.async_api import async_playwright

BASE = "http://localhost:8088"
OUT = r"C:\workspace\pea\verify"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        
        # Step 1: Login via form
        await page.goto(BASE + "/login", timeout=15000)
        await page.wait_for_timeout(2000)
        
        inputs = await page.locator("input").all()
        print(f"Found {len(inputs)} inputs")
        
        if len(inputs) >= 2:
            await inputs[0].fill("test@test.com")
            await inputs[1].fill("test")
            
            buttons = await page.locator("button").all()
            for btn in buttons:
                txt = (await btn.inner_text()).strip()
                print(f"Button: {txt}")
                if "\u767b\u5f55" in txt and "\u6ce8\u518c" not in txt:
                    await btn.click()
                    break
            
            await page.wait_for_timeout(5000)
            print(f"After login URL: {page.url}")
        
        if "login" in page.url.lower():
            print("Login failed with pw=test, trying test123456...")
            inputs = await page.locator("input").all()
            if len(inputs) >= 2:
                await inputs[0].fill("test@test.com")
                await inputs[1].fill("test123456")
                buttons = await page.locator("button").all()
                for btn in buttons:
                    txt = (await btn.inner_text()).strip()
                    if "\u767b\u5f55" in txt:
                        await btn.click()
                        break
                await page.wait_for_timeout(5000)
                print(f"After retry URL: {page.url}")
        
        await page.screenshot(path=f"{OUT}/shot_fix_login_state.png")
        
        # Step 2: Create canvas (if logged in)
        if "login" not in page.url.lower():
            cvs_data = await page.evaluate("""() => {
                return fetch('/api/canvases', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({title: 'editor-fix-final', type: 'personal'})
                }).then(r => r.json()).catch(e => ({err: String(e)}));
            }""")
            print(f"Canvas: {json.dumps(cvs_data)[:300]}")
            
            cvs_id = None
            if isinstance(cvs_data, dict) and cvs_data.get("id"):
                cvs_id = cvs_data["id"]
            
            if cvs_id:
                sid = str(cvs_id)
                await page.goto(BASE + "/canvas/" + sid, timeout=15000)
                await page.wait_for_timeout(4000)
                
                # Setup canvas state
                setup = "(function(){var ui=window.__ui?window.__ui.getState():null;var cs=window.__canvas?window.__canvas.getState():null;if(!ui||!cs)return{err:'no store'};try{ui.setActive('canvas');cs.setCanvasMeta('" + sid + "',1,'v2');cs.loadGraph([{id:'n1',type:'pea',position:{x:400,y:300},data:{kind:'image',label:'Img'}}],[],1);cs.setSelection(['n1']);return{ok:1}}catch(e){return{err:String(e)}}})()"
                sr = await page.evaluate(setup)
                print(f"Setup: {sr}")
                await page.wait_for_timeout(2000)
                
                # Screenshot and probe
                await page.screenshot(path=f"{OUT}/shot_fix_light_editor.png", full_page=False)
                
                info = await page.evaluate("""(function(){
                    var ed=document.querySelector('.node-prompt-editor');
                    if(!ed)return{err:'no editor'};
                    var s=getComputedStyle(ed);
                    return{color:s.color,bg:s.backgroundColor,caretColor:s.caretColor,h:ed.offsetHeight,place:(ed.getAttribute('data-placeholder')||'').substring(0,50),htmlLen:ed.innerHTML.length};
                })()""")
                print(f"\nEditor probe:\n{json.dumps(info, indent=2)}")
                
                # Type text
                ed_loc = page.locator(".node-prompt-editor")
                cnt = await ed_loc.count()
                print(f"\nEditor count: {cnt}")
                
                if cnt > 0:
                    await ed_loc.first.click()
                    await page.wait_for_timeout(300)
                    await page.keyboard.type("Light theme text test - should be visible!")
                    await page.wait_for_timeout(500)
                    await page.screenshot(path=f"{OUT}/shot_fix_light_editor_typed.png", full_page=False)
                    
                    final = await page.evaluate("""(function(){
                        var e=document.querySelector('.node-prompt-editor');
                        return e?{color:getComputedStyle(e).color,text:e.innerText}:null;
                    })()""")
                    print(f"Typed result: {json.dumps(final)}")
        else:
            print("Cannot log in - skipping editor verification")
        
        await browser.close()
        print("\nDone!")

asyncio.run(main())
