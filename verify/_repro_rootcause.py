"""
决定性复现「提交时保存失败 + 删除草稿兜底」导致 re-entry 丢提示词：
  建画布 -> 视频节点 -> 打字 -> 强制 version 冲突(让 saveCanvasNow 409)
  -> 真点生成(submit 会 saveCanvasNow[409] + localStorage.removeItem 兜底)
  -> 检查 后端editorText / localStorage草稿 是否都没了
  -> reload（退出再进）-> openCanvas -> 点节点 -> 编辑器应为空(复现!)
"""
import asyncio, json, time
from playwright.async_api import async_playwright

URL="http://localhost:8088"; EMAIL="v3test@test.com"; PWD="Test123456"
SENTINEL=f"PEA_RC_{int(time.time())}_戴帽小猫雪地打滚"

def log(m): print(f"[RC] {m}", flush=True)

async def get_backend_editor(page, cid):
    js="""(async function(cid){
        var token=localStorage.getItem('pea_token');var h={};if(token){h['Authorization']='Bearer '+token;}
        var r=await fetch('/api/canvases/'+cid,{headers:h});var j=await r.json();
        var g=(typeof j.graph_json==='string')?JSON.parse(j.graph_json):(j.graph_json||{});
        var ns=g.nodes||[];var n=null;for(var i=0;i<ns.length;i++){if(ns[i].id==='vX'){n=ns[i];break;}}
        return {ok:r.status, editorText:(n&&n.data&&n.data.meta)?n.data.meta.editorText:null};
    })()"""
    return await page.evaluate(js, cid)

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
        cid=await page.evaluate("""async()=>{const t=localStorage.getItem('pea_token');const r=await fetch('/api/canvases',{method:'POST',headers:{'Content-Type':'application/json',...(t?{Authorization:'Bearer '+t}:{})},body:JSON.stringify({title:'rc',scope:'personal'})});return (await r.json()).id;}""")
        log(f"画布 id={cid}")
        await open_canvas(page, cid)
        await page.evaluate("""()=>{window.__canvas.setState({nodes:[{id:'vX',type:'pea',position:{x:400,y:300},data:{kind:'video',label:'Video',prompt:'',generating:false,meta:{}}}],edges:[],dirty:true});window.__canvas.getState().select('vX');}""")
        await page.wait_for_timeout(2000)
        ed=page.locator('.node-prompt-editor').first
        await ed.click(); await ed.type(SENTINEL, delay=20); await page.wait_for_timeout(800)

        # 强制 version 冲突：把本地 version 改成一个服务端不可能接受的值
        await page.evaluate("()=>{window.__canvas.setState({version: 999999});}")
        log("已强制 version=999999（让 saveCanvasNow 409）")

        # 真点生成（submit 会 saveCanvasNow[409被吞] + localStorage.removeItem 兜底）
        launcher=page.locator('.pe-launcher').first
        disabled = await launcher.evaluate("el=>el.className.includes('disabled')")
        log(f"生成按钮 disabled={disabled}")
        if disabled: log("!!! 无法生成，终止"); await b.close(); return
        await launcher.click()
        await page.wait_for_timeout(2500)

        # 检查保存结果
        be=await get_backend_editor(page, cid)
        ls=await page.evaluate("""()=>{const cid=window.__canvas.getState().canvasId;return localStorage.getItem('pea:draft:'+cid+':vX');}""")
        log(f"【提交后】后端 editorText = {json.dumps(be.get('editorText'), ensure_ascii=False)} (http {be.get('ok')})")
        log(f"【提交后】localStorage 草稿 = {json.dumps(ls, ensure_ascii=False)}  (submit 应已 removeItem)")

        # reload（退出再进）
        log(">>> reload（退出项目再进来）")
        await page.reload(wait_until="networkidle")
        await ensure_login(page)
        await page.wait_for_function("typeof window.__canvas!=='undefined'", timeout=15000)
        await page.wait_for_timeout(800)
        await open_canvas(page, cid)
        await page.evaluate("()=>window.__canvas.getState().select('vX')")
        try: await page.wait_for_selector('.node-prompt-editor', timeout=8000)
        except Exception as e: log("编辑器未挂载: "+str(e))
        await page.wait_for_timeout(1500)
        after=await page.evaluate("""()=>{const ed=document.querySelector('.node-prompt-editor');const n=window.__canvas.getState().nodes.find(x=>x.id==='vX');return {editorVisible: ed?ed.innerText:'(no editor)', editorText: n?.data?.meta?.editorText};}""")
        log(f"【re-entry 点节点后】编辑器 = {json.dumps(after.get('editorVisible'), ensure_ascii=False)}")
        ok = SENTINEL in (after.get('editorVisible') or "")
        log("="*60)
        log(f"后端没存到editorText? {'是(保存失败)' if not be.get('editorText') else '否'}")
        log(f"localStorage兜底被删? {'是' if ls is None else '否'}")
        log("re-entry 后提示词: "+("保留 ✅" if ok else "丢失 ❌ (复现成功!)"))
        log("="*60)
        await b.close()

asyncio.run(main())
