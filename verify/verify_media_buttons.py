import sys, time, datetime
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
EMAIL = f"e{int(time.time())}@pea.ai"
PW = "password123"

def log(*a):
    print(*a, flush=True)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 900})
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector('input[placeholder="you@pea.ai"]', timeout=10000)

        # 切换到注册模式
        page.get_by_role("button", name="没有账号？去注册").click(timeout=8000)
        page.wait_for_selector('input[placeholder="可选"]', timeout=8000)

        # 注册
        page.fill('input[placeholder="you@pea.ai"]', EMAIL)
        page.fill('input[placeholder="至少 8 位"]', PW)
        page.fill('input[placeholder="可选"]', "验证员")
        page.locator('form button[type="submit"]').click(timeout=8000)
        page.wait_for_timeout(1500)
        token = page.evaluate("() => localStorage.getItem('pea_token') || ''")
        log("token:", bool(token))

        # 建画布
        cid = page.evaluate("""async () => {
            const r = await fetch('/canvases', {method:'POST', headers:{'content-type':'application/json','authorization':'Bearer '+localStorage.getItem('pea_token')}, body: JSON.stringify({title:'media-verify', scope:'personal'})});
            const j = await r.json(); return j.data?.id || j.id || null;
        }""")
        log("canvas:", cid)

        # 启用 dev hooks（暴露 window.__canvas/__ui），刷新使其生效
        page.evaluate("() => { localStorage.setItem('__peaDevHooks', '1'); }")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        page.evaluate("""(cid) => { window.__canvas.getState().openCanvas(cid); window.__ui.getState().setActive('canvas'); }""", cid)
        page.wait_for_timeout(1000)

        # 注入：AI 单图(nAi) + 上传图(nUp) + AI 多图(nAiM)
        page.evaluate("""() => {
            const ai = { id:'nAi', type:'pea', position:{x:60,y:100}, data:{ kind:'image', resultUrl:'https://placehold.co/200x200/22c55e/fff?text=AI', label:'AI', prompt:'ai' } };
            const up = { id:'nUp', type:'pea', position:{x:420,y:100}, data:{ kind:'image', url:'https://placehold.co/200x200/ef4444/fff?text=Upload', fileKey:'k1', label:'Upload' } };
            const aiM = { id:'nAiM', type:'pea', position:{x:780,y:100}, data:{ kind:'image', resultUrls:['https://placehold.co/120x120/22c55e/fff?text=1','https://placehold.co/120x120/3b82f6/fff?text=2','https://placehold.co/120x120/ef4444/fff?text=3','https://placehold.co/120x120/eab308/fff?text=4'], resultIndex:0, label:'AIM', prompt:'ai-multi' } };
            window.__canvas.getState().loadGraph([ai, up, aiM], [], 1);
        }""")
        page.wait_for_timeout(1200)

        def star(n):
            return page.locator(f".react-flow__node[data-id='{n}'] .pea-node-result-star").count()
        def repl(n):
            # 同时统计 toolbar 替换按钮 + 右上角常驻替换按钮
            return (page.locator(f".react-flow__node[data-id='{n}'] .pea-node-toolbar-btn[title='替换']").count()
                    + page.locator(f".react-flow__node[data-id='{n}'] .pea-node-result-replace").count())
        def badge(n):
            return page.locator(f".react-flow__node[data-id='{n}'] .pea-node-image-badge").count()

        star_ai, repl_ai = star("nAi"), repl("nAi")
        star_up, repl_up = star("nUp"), repl("nUp")
        badge_aim = badge("nAiM")
        log(f"AI单图:  收藏星标={star_ai}  替换={repl_ai}")
        log(f"上传图:   收藏星标={star_up}  替换={repl_up}")
        log(f"AI多图:   多图角标={badge_aim}")

        ok = (star_ai == 1 and repl_ai == 0 and star_up == 0 and repl_up >= 1 and badge_aim == 1)
        log("总 console error 数:", len(errs))
        for e in errs[:10]:
            log("  ERR:", e[:200])
        log("验证通过" if ok else "验证失败")
        b.close()
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
