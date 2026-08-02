"""
E2E：视频节点提示词「重启容器后不丢失」验证
流程：登录 -> 建画布 -> 真实打字进视频节点编辑器 -> 等落库 -> 断言 MySQL(graph_json)含 prompt
      -> docker restart web 容器 -> 重载 -> 重新打开画布 -> 断言 prompt 仍在(存储+DOM)
"""
import asyncio, sys, subprocess, time, json
from playwright.async_api import async_playwright

URL = 'http://localhost:8088'
EMAIL = 'v3test@test.com'
PWD = 'Test123456'
PROMPT = 'PERSIST_CHECK_月球猫跳舞_8f3a'

def log(m): print(f'[E2E] {m}', flush=True)

async def ensure_login(page):
    # 先导航建立 origin，否则 about:blank 下读 localStorage 会被浏览器拒绝
    await page.goto(URL, wait_until='domcontentloaded', timeout=20000)
    await asyncio.sleep(1)
    # token 在 localStorage，重载后通常仍在；不在则走登录
    tok = await page.evaluate("localStorage.getItem('pea_token')")
    if tok:
        log('已有 token，跳过登录')
        await asyncio.sleep(2)
        return
    log('执行登录')
    await asyncio.sleep(1)
    try:
        await page.fill('input[placeholder*="you@"]', EMAIL, timeout=5000)
        await page.fill('input[placeholder*="至少"]', PWD, timeout=5000)
        await page.press('input[placeholder*="至少"]', 'Enter')
    except Exception as e:
        log(f'登录填充异常(可能已登录): {e}')
    await asyncio.sleep(3)

async def open_canvas(page, cid):
    await page.evaluate("""
        async (cid) => {
            let a=0;
            while (typeof window.__canvas === 'undefined' && a<40){ await new Promise(r=>setTimeout(r,500)); a++; }
            await window.__canvas.getState().openCanvas(cid);
            const ui = window.__ui;
            if (ui && ui.getState && ui.getState().setActive) ui.getState().setActive('canvas');
        }
    """, cid)
    await asyncio.sleep(3)

async def api_graph(page, cid):
    return await page.evaluate("""
        async (cid) => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases/'+cid, {headers: token?{Authorization:'Bearer '+token}:{}});
            const j = await r.json();
            return typeof j.graph_json === 'string' ? j.graph_json : JSON.stringify(j.graph_json);
        }
    """, cid)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width':1400,'height':900})
        await page.add_init_script("localStorage.setItem('__peaDevHooks','1');")

        await ensure_login(page)

        # 建画布
        cid = await page.evaluate("""
            async () => {
                const token = localStorage.getItem('pea_token');
                const r = await fetch('/api/canvases', {method:'POST',
                    headers:{'Content-Type':'application/json', ...(token?{Authorization:'Bearer '+token}:{})},
                    body: JSON.stringify({title:'e2e_persist', scope:'personal'})});
                return (await r.json()).id;
            }
        """)
        log(f'canvas id = {cid}')

        await open_canvas(page, cid)

        # 注入一个无 fileKey 的视频节点并选中
        await page.evaluate("""
            () => {
                window.__canvas.setState({
                    nodes:[{id:'nVid', type:'pea', position:{x:400,y:250},
                        data:{kind:'video', label:'Video', prompt:'', generating:false,
                               resultUrl:undefined, resultUrls:undefined, meta:{}}}],
                    edges:[], version:1, dirty:true
                });
                const st = window.__canvas.getState();
                if (st.select) st.select('nVid');
            }
        """)
        await asyncio.sleep(1.5)

        # 真实打字进编辑器
        editor = page.locator('.node-prompt-editor').first
        assert await editor.count() > 0, '编辑器未出现'
        await editor.click()
        await asyncio.sleep(0.3)
        await editor.type(PROMPT, delay=20)
        await asyncio.sleep(1)

        dom_text = await editor.inner_text()
        log(f'打字后 DOM: "{dom_text}"')
        assert PROMPT in dom_text, '打字未进入 DOM'

        # 等防抖提交 + 显式落库
        await asyncio.sleep(3)
        saved = await page.evaluate("() => window.__canvas.getState().saveCanvasNow()")
        log(f'saveCanvasNow 返回: {saved}')
        await asyncio.sleep(1)

        # 断言 A：MySQL(graph_json) 含 prompt
        g = await api_graph(page, cid)
        if PROMPT in g:
            log('断言A 通过：MySQL graph_json 含 prompt（后端持久化 OK）')
        else:
            log('断言A 失败：MySQL 未持久化 prompt !!!')
            await page.screenshot(path='verify/shot_e2e_assertA_fail.png')
            await browser.close()
            sys.exit(2)

        # —— 关键：docker restart web 容器（模拟用户重启）——
        log('>>> docker restart pea-server-web-1 ...')
        subprocess.run(['docker','restart','pea-server-web-1'], check=True)
        # 等容器+nginx 恢复
        up = False
        for i in range(40):
            try:
                async with async_playwright() as _p:
                    pass
            except Exception:
                pass
            code = subprocess.run(['curl','-s','-o','/dev/null','-w','%{http_code}','http://localhost:8088/'],
                                  capture_output=True, text=True).stdout.strip()
            if code == '200':
                up = True; log(f'web 已恢复 (尝试 {i+1})'); break
            await asyncio.sleep(2)
        if not up:
            log('web 未恢复，终止'); await browser.close(); sys.exit(3)
        await asyncio.sleep(2)

        # 重载页面（同一 browser 上下文，localStorage 保留）
        await page.reload(wait_until='networkidle', timeout=20000)
        await asyncio.sleep(2)
        await ensure_login(page)
        await open_canvas(page, cid)
        await asyncio.sleep(2)
        # 真实用户重开画布后通常会点一下节点 -> 显式选中，验证回填路径
        await page.evaluate("() => { const s=window.__canvas.getState(); if(s.select) s.select('nVid'); }")
        await asyncio.sleep(2)
        sel = await page.evaluate("() => window.__canvas.getState().selectedId")
        ec = await page.locator('.node-prompt-editor').count()
        log(f'重载后 selectedId={sel} editorCount={ec}')

        # 断言 B：重载后 store 里 prompt 还在
        node = await page.evaluate("""
            () => {
                const st = window.__canvas.getState();
                const n = st.nodes.find(x=>x.id==='nVid');
                if (!n) return null;
                return { prompt: n.data?.prompt, editorText: n.data?.meta?.editorText };
            }
        """)
        log(f'重载后 store 节点: {json.dumps(node, ensure_ascii=False)}')
        store_ok = node and (PROMPT in (node.get('prompt') or '') or PROMPT in (node.get('editorText') or ''))

        # 断言 C：DOM 编辑器里也能看到
        dom_after = ''
        try:
            ed = page.locator('.node-prompt-editor').first
            if await ed.count() > 0:
                dom_after = await ed.inner_text()
        except Exception as e:
            log(f'读 DOM 异常: {e}')
        dom_ok = PROMPT in dom_after

        if store_ok and dom_ok:
            log('断言B/C 通过：重启容器 + 重载后 prompt 仍在（store + DOM）✅')
            log('RESULT: PASS')
        else:
            log(f'断言失败：store_ok={store_ok} dom_ok={dom_ok} dom="{dom_after}"')
            await page.screenshot(path='verify/shot_e2e_assertB_fail.png')
            log('RESULT: FAIL')
            await browser.close()
            sys.exit(4)

        await browser.close()

asyncio.run(main())
