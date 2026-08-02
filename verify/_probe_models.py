import asyncio, json
from playwright.async_api import async_playwright
URL="http://localhost:8088"; EMAIL="v3test@test.com"; PWD="Test123456"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        page=await b.new_page(viewport={'width':1400,'height':900})
        await page.add_init_script("localStorage.setItem('__peaDevHooks','1');")
        await page.goto(URL, wait_until="networkidle")
        try:
            await page.fill('input[placeholder*="you@"]', EMAIL)
            await page.fill('input[type="password"]', PWD)
            await page.press('input[type="password"]','Enter'); await page.wait_for_timeout(3000)
        except Exception as e: print("login:",e)
        await page.wait_for_function("typeof window.__canvas!=='undefined'", timeout=15000)
        cid=await page.evaluate("""async()=>{const t=localStorage.getItem('pea_token');const r=await fetch('/api/canvases',{method:'POST',headers:{'Content-Type':'application/json',...(t?{Authorization:'Bearer '+t}:{})},body:JSON.stringify({title:'m',scope:'personal'})});return (await r.json()).id;}""")
        await page.evaluate("""async(cid)=>{let a=0;while(typeof window.__canvas==='undefined'&&a<30){await new Promise(r=>setTimeout(r,500));a++}await window.__canvas.getState().openCanvas(cid);const ui=window.__ui;if(ui&&ui.getState&&ui.getState().setActive)ui.getState().setActive('canvas');}""",cid)
        await page.wait_for_timeout(3000)
        await page.evaluate("""()=>{window.__canvas.setState({nodes:[{id:'vM',type:'pea',position:{x:400,y:300},data:{kind:'video',label:'Video',prompt:'',generating:false,meta:{}}}],edges:[],dirty:true});window.__canvas.getState().select('vM');}""")
        await page.wait_for_timeout(3500)
        info=await page.evaluate("""()=>{
           const chip=document.querySelector('.node-input-model-chip');
           const launcher=document.querySelector('.pe-launcher');
           return { chipText: chip?chip.innerText.replace(/\s+/g,' ').trim():'(none)', launcherDisabled: launcher?launcher.className.includes('disabled'):null };
        }""")
        print("MODEL CHIP:", json.dumps(info, ensure_ascii=False))
        await b.close()
asyncio.run(main())
