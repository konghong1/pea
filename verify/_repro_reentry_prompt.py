"""
忠实复现 + 后端取证：
  登录 -> 建画布 -> 加视频节点 -> 真实输入提示词 -> 落盘
  -> 直接 GET 后端确认 editorText 是否真的写进去了
  -> 整页 reload（退出项目再进来）
  -> 重新 openCanvas -> GET 后端确认加载回来没有 -> 点节点 -> 读编辑器
"""
import asyncio, json, sys, time
from playwright.async_api import async_playwright

URL = "http://localhost:8088"
EMAIL = "v3test@test.com"
PWD = "Test123456"
SENTINEL = f"PEA_REENTRY_{int(time.time())}_小猫戴帽子在雪地打滚"

def log(m): print(f"[REPRO] {m}", flush=True)

async def get_backend_editor(page, cid):
    js = """
    (async function(cid){
        var token = localStorage.getItem('pea_token');
        var headers = {};
        if (token) { headers['Authorization'] = 'Bearer ' + token; }
        var r = await fetch('/api/canvases/' + cid, { headers: headers });
        var j = await r.json();
        var g = (typeof j.graph_json === 'string') ? JSON.parse(j.graph_json) : (j.graph_json || {});
        var nodes = g.nodes || [];
        var n = null;
        for (var i = 0; i < nodes.length; i++) { if (nodes[i].id === 'vRe') { n = nodes[i]; break; } }
        var et = (n && n.data && n.data.meta) ? n.data.meta.editorText : null;
        return { ok: r.status, editorText: et };
    })
    """
    return await page.evaluate(js, cid)

async def ensure_login(page):
    try:
        await page.wait_for_selector('input[placeholder*="you@"]', timeout=4000)
        await page.fill('input[placeholder*="you@"]', EMAIL)
        await page.fill('input[type="password"]', PWD)
        await page.press('input[type="password"]', 'Enter')
        await page.wait_for_timeout(3000)
        log("已登录")
    except Exception as e:
        log(f"无登录框(可能已登录): {e}")

async def open_canvas(page, cid):
    await page.evaluate("""async (cid) => {
        let a=0; while (typeof window.__canvas==='undefined' && a<30){await new Promise(r=>setTimeout(r,500));a++;}
        await window.__canvas.getState().openCanvas(cid);
        const ui = window.__ui; if (ui && ui.getState && ui.getState().setActive) ui.getState().setActive('canvas');
    }""", cid)
    await page.wait_for_timeout(4000)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page(viewport={'width': 1400, 'height': 900})
        await page.add_init_script("localStorage.setItem('__peaDevHooks','1');")
        page.on("pageerror", lambda e: log("PAGEERROR: " + str(e)))
        page.on("console", lambda m: log("CONSOLE.ERR: " + m.text) if m.type == "error" else None)

        await page.goto(URL, wait_until="networkidle", timeout=20000)
        await ensure_login(page)
        await page.wait_for_function("typeof window.__canvas !== 'undefined'", timeout=15000)
        await page.wait_for_timeout(500)

        cid = await page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {method:'POST',
                headers:{'Content-Type':'application/json', ...(token?{Authorization:'Bearer '+token}:{})},
                body: JSON.stringify({title:'reentry_test', scope:'personal'})});
            return (await r.json()).id;
        }""")
        log(f"画布 id = {cid}")
        await open_canvas(page, cid)

        await page.evaluate("""() => {
            window.__canvas.setState({ nodes:[{id:'vRe',type:'pea',position:{x:400,y:300},
                data:{kind:'video',label:'Video',prompt:'',generating:false,resultUrl:undefined,resultUrls:undefined,meta:{}}}],
                edges:[], dirty:true });
            window.__canvas.getState().select('vRe');
        }""")
        await page.wait_for_timeout(1500)

        editor = page.locator('.node-prompt-editor').first
        if await editor.count() == 0:
            log("!!! 编辑器未出现"); await b.close(); return
        await editor.click()
        await editor.type(SENTINEL, delay=20)
        await page.wait_for_timeout(800)

        await page.evaluate("() => window.__canvas.getState().saveCanvasNow()")
        await page.wait_for_timeout(1500)

        mem = await page.evaluate("""() => {
            const n = window.__canvas.getState().nodes.find(x=>x.id==='vRe');
            const ed = document.querySelector('.node-prompt-editor');
            return { editorText: n?.data?.meta?.editorText, editorVisible: ed?ed.innerText:'(none)' };
        }""")
        log("【内存】store.editorText = " + json.dumps(mem.get('editorText'), ensure_ascii=False))
        log("【内存】编辑器可见 = " + json.dumps(mem.get('editorVisible'), ensure_ascii=False))

        be1 = await get_backend_editor(page, cid)
        log("【后端·落盘后】editorText = " + json.dumps(be1.get('editorText'), ensure_ascii=False) + f"  (http {be1.get('ok')})")

        # ===== 退出项目再进来：整页 reload =====
        log(">>> 整页 reload（退出项目再进来）...")
        await page.reload(wait_until="networkidle", timeout=20000)
        await ensure_login(page)
        await page.wait_for_function("typeof window.__canvas !== 'undefined'", timeout=15000)
        await page.wait_for_timeout(800)
        await open_canvas(page, cid)

        be2 = await get_backend_editor(page, cid)
        log("【后端·reload后】editorText = " + json.dumps(be2.get('editorText'), ensure_ascii=False) + f"  (http {be2.get('ok')})")

        mem_after_load = await page.evaluate("""() => {
            const n = window.__canvas.getState().nodes.find(x=>x.id==='vRe');
            return { editorText: n?.data?.meta?.editorText };
        }""")
        log("【内存·点节点前】store.editorText = " + json.dumps(mem_after_load.get('editorText'), ensure_ascii=False))

        await page.evaluate("() => window.__canvas.getState().select('vRe')")
        try:
            await page.wait_for_selector('.node-prompt-editor', timeout=8000)
        except Exception as e:
            log("编辑器未挂载: " + str(e))
        await page.wait_for_timeout(1500)
        after = await page.evaluate("""() => {
            const ed = document.querySelector('.node-prompt-editor');
            const n = window.__canvas.getState().nodes.find(x=>x.id==='vRe');
            return { editorVisible: ed?ed.innerText:'(no editor)', storeEditorText: n?.data?.meta?.editorText };
        }""")
        log("【点节点后】编辑器可见 = " + json.dumps(after.get('editorVisible'), ensure_ascii=False))
        log("【点节点后】store.editorText = " + json.dumps(after.get('storeEditorText'), ensure_ascii=False))

        ok = SENTINEL in (after.get('editorVisible') or '')
        log("=" * 60)
        log("后端落盘有editorText? " + ("是" if be1.get('editorText') else "否(保存失败!)"))
        log("后端reload后有editorText? " + ("是" if be2.get('editorText') else "否(加载丢失!)"))
        log("RESULT: " + ("✅ 提示词保留" if ok else "❌ 提示词丢失"))
        log("=" * 60)
        await b.close()

asyncio.run(main())
