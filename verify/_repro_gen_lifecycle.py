"""
完整生命周期复现（用户真实路径）：
  建画布 -> 视频节点 -> 打字 -> 真点"生成" -> 观察生成中/完成后 编辑器+editorText
  -> 整页 reload（退出再进）-> 重新 openCanvas -> 点节点 -> 读编辑器
重点：捕获「生成过程中」和「re-entry 后」两个时间点提示词是否丢失，以及 editorText 在 store/后端的真实状态。
"""
import asyncio, json, time
from playwright.async_api import async_playwright

URL="http://localhost:8088"; EMAIL="v3test@test.com"; PWD="Test123456"
SENTINEL=f"PEA_GEN_{int(time.time())}_戴帽小猫雪地打滚"

def log(m): print(f"[LIFE] {m}", flush=True)

async def get_store(page):
    return await page.evaluate("""() => {
        const n = window.__canvas.getState().nodes.find(x=>x.id==='vG');
        const ed = document.querySelector('.node-prompt-editor');
        const gen = n ? n.data.generating : null;
        const ru = n ? (n.data.resultUrl||n.data.resultUrls||null) : null;
        return {
            generating: gen, resultUrl: ru,
            editorText: n?.data?.meta?.editorText,
            editorVisible: ed ? ed.innerText : '(no editor)',
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

        cid=await page.evaluate("""async()=>{const t=localStorage.getItem('pea_token');const r=await fetch('/api/canvases',{method:'POST',headers:{'Content-Type':'application/json',...(t?{Authorization:'Bearer '+t}:{})},body:JSON.stringify({title:'genlife',scope:'personal'})});return (await r.json()).id;}""")
        log(f"画布 id={cid}")
        await open_canvas(page, cid)

        await page.evaluate("""()=>{window.__canvas.setState({nodes:[{id:'vG',type:'pea',position:{x:400,y:300},data:{kind:'video',label:'Video',prompt:'',generating:false,meta:{}}}],edges:[],dirty:true});window.__canvas.getState().select('vG');}""")
        await page.wait_for_timeout(2000)

        ed=page.locator('.node-prompt-editor').first
        await ed.click(); await ed.type(SENTINEL, delay=20); await page.wait_for_timeout(800)
        log("【打字后】"+json.dumps(await get_store(page), ensure_ascii=False))

        # 真点生成
        launcher=page.locator('.pe-launcher').first
        disabled = await launcher.evaluate("el=>el.className.includes('disabled')")
        log(f"生成按钮 disabled={disabled}")
        if disabled:
            log("!!! 生成按钮 disabled，无法生成，终止")
            await b.close(); return
        await launcher.click()
        log(">>> 已点击生成")
        await page.wait_for_timeout(3000)
        log("【生成中(3s)】"+json.dumps(await get_store(page), ensure_ascii=False))

        # 轮询等待完成（最多 90s）
        done=False
        for i in range(30):
            s=await get_store(page)
            if s["generating"] is False and (s["resultUrl"] or s["editorText"] is None):
                # 完成
                done=True; log(f"【轮询{i+1} 完成】"+json.dumps(s, ensure_ascii=False)); break
            if s["generating"] is False and s["resultUrl"]:
                done=True; log(f"【轮询{i+1} 完成】"+json.dumps(s, ensure_ascii=False)); break
            await page.wait_for_timeout(3000)
        if not done:
            s=await get_store(page); log("【超时未完】"+json.dumps(s, ensure_ascii=False))

        s=await get_store(page)
        log("【生成结束后】"+json.dumps(s, ensure_ascii=False))
        ok1 = SENTINEL in (s["editorVisible"] or "")
        log("生成结束后编辑器是否含提示词: "+("是" if ok1 else "否!!!"))

        # ===== 退出再进：reload =====
        log(">>> reload（退出项目再进来）")
        await page.reload(wait_until="networkidle")
        await ensure_login(page)
        await page.wait_for_function("typeof window.__canvas!=='undefined'", timeout=15000)
        await page.wait_for_timeout(800)
        await open_canvas(page, cid)
        await page.evaluate("()=>window.__canvas.getState().select('vG')")
        try: await page.wait_for_selector('.node-prompt-editor', timeout=8000)
        except Exception as e: log("编辑器未挂载: "+str(e))
        await page.wait_for_timeout(1500)
        s2=await get_store(page)
        log("【re-entry 点节点后】"+json.dumps(s2, ensure_ascii=False))
        ok2 = SENTINEL in (s2["editorVisible"] or "")
        log("="*60)
        log("生成结束提示词保留? "+("是" if ok1 else "否"))
        log("re-entry 后提示词保留? "+("是" if ok2 else "否(复现!)"))
        log("="*60)
        await b.close()

asyncio.run(main())
