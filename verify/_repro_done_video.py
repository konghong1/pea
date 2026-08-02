"""
专门复现「已完成视频(resultUrl)节点」的 re-entry：
  建画布 -> 视频节点 -> 打字 -> 标记完成(带 resultUrl) -> 落盘
  -> reload（退出再进）-> openCanvas -> 点节点 -> 读编辑器
目的：确认「已完成视频 + 提示词」节点在重新进入项目后，下方编辑栏是否还能还原提示词。
"""
import asyncio, json, time
from playwright.async_api import async_playwright

URL="http://localhost:8088"; EMAIL="v3test@test.com"; PWD="Test123456"
SENTINEL=f"PEA_DONE_{int(time.time())}_戴帽小猫雪地打滚"

def log(m): print(f"[DONE] {m}", flush=True)

async def get_store(page):
    return await page.evaluate("""() => {
        const n = window.__canvas.getState().nodes.find(x=>x.id==='vD');
        const ed = document.querySelector('.node-prompt-editor');
        return {
            generating: n?n.data.generating:null,
            resultUrl: n?(n.data.resultUrl||n.data.resultUrls||null):null,
            editorText: n?.data?.meta?.editorText,
            editorVisible: ed?ed.innerText:'(no editor)',
            hasEditorEl: !!ed
        };
    }""")

async def ensure_login(page):
    try:
        await page.wait_for_selector('input[placeholder*="you@"]', timeout=4000)
        await page.fill('input[placeholder*="you@"]', EMAIL)
        await page.fill('input[type="password"]', PWD)
        await page.press('input[type="password"]','Enter'); await page.wait_for_timeout(3000)
    except Exception as e: log("无登录框(已登录?): "+str(e))

async def open_canvas(page, cid):
    await page.evaluate("""async(cid)=>{let a=0;while(typeof window.__canvas==='undefined'&&a<30){await new Promise(r=>setTimeout(r,500));a++}await window.__canvas.getState().openCanvas(cid);const ui=window.__ui;if(ui&&ui.getState&&ui.getState().setActive)ui.getState().setActive('canvas');}""", cid)
    await page.wait_for_timeout(4000)

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        page=await b.new_page(viewport={'width':1400,'height':900})
        await page.add_init_script("localStorage.setItem('__peaDevHooks','1');")
        page.on("pageerror", lambda e: log("PAGEERROR: "+str(e)))
        page.on("console", lambda m: log("CONSOLE.ERR: "+m.text) if m.type=="error" else None)
        await page.goto(URL, wait_until="networkidle")
        await ensure_login(page)
        await page.wait_for_function("typeof window.__canvas!=='undefined'", timeout=15000)
        await page.wait_for_timeout(500)
        cid=await page.evaluate("""async()=>{const t=localStorage.getItem('pea_token');const r=await fetch('/api/canvases',{method:'POST',headers:{'Content-Type':'application/json',...(t?{Authorization:'Bearer '+t}:{})},body:JSON.stringify({title:'donevid',scope:'personal'})});return (await r.json()).id;}""")
        log(f"画布 id={cid}")
        await open_canvas(page, cid)
        await page.evaluate("""()=>{window.__canvas.setState({nodes:[{id:'vD',type:'pea',position:{x:400,y:300},data:{kind:'video',label:'Video',prompt:'',generating:false,meta:{}}}],edges:[],dirty:true});window.__canvas.getState().select('vD');}""")
        await page.wait_for_timeout(2000)
        ed=page.locator('.node-prompt-editor').first
        await ed.click(); await ed.type(SENTINEL, delay=20); await page.wait_for_timeout(800)
        # 标记完成：模拟视频生成结束，回填 resultUrl + editorText
        await page.evaluate("""() => {
            const st = window.__canvas.getState();
            const n = st.nodes.find(x=>x.id==='vD');
            st.updateNodeData('vD', { generating:false, resultUrl:'https://example.com/fake_video.mp4', resultUrls:['https://example.com/fake_video.mp4'], prompt: n.data.meta.editorText });
            window.__canvas.getState().saveCanvasNow();
        }""")
        await page.wait_for_timeout(1200)
        log("【标记完成后】"+json.dumps(await get_store(page), ensure_ascii=False))

        log(">>> reload（退出项目再进来）")
        await page.reload(wait_until="networkidle")
        await ensure_login(page)
        await page.wait_for_function("typeof window.__canvas!=='undefined'", timeout=15000)
        await page.wait_for_timeout(800)
        await open_canvas(page, cid)
        await page.evaluate("()=>window.__canvas.getState().select('vD')")
        try: await page.wait_for_selector('.node-prompt-editor', timeout=8000)
        except Exception as e: log("编辑器未挂载: "+str(e))
        await page.wait_for_timeout(1500)
        s2=await get_store(page)
        log("【re-entry 点节点后】"+json.dumps(s2, ensure_ascii=False))
        ok = SENTINEL in (s2["editorVisible"] or "")
        log("="*60)
        log("re-entry 后「已完成视频节点」下方编辑栏是否含提示词: "+("是 ✅" if ok else "否 ❌ (复现!)"))
        log("="*60)
        await b.close()

asyncio.run(main())
