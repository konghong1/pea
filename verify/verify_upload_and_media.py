import sys, time, os
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
EMAIL = f"e{int(time.time())}@pea.ai"
PW = "password123"
TEST_IMG = "D:/workspace/pea/pea-server/web/public/e2e-test.png"

def log(*a):
    print(*a, flush=True)

def main():
    errs = []
    upload_ok = False
    ai_repl = 0
    up_repl = 0
    ai_star = 0
    up_star = 0
    badge_count = 0
    lightbox_ok = False

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 900})
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        # 监听 /files/upload 响应
        def handle_route(route, request):
            nonlocal upload_ok
            if request.url.endswith("/files/upload") and request.method == "POST":
                resp = route.fetch()
                if 200 <= resp.status < 300:
                    upload_ok = True
                else:
                    log("upload response status:", resp.status, resp.body()[:200])
                route.fulfill(response=resp)
            else:
                route.continue_()
        page.route("**/files/upload", handle_route)

        page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector('input[placeholder="you@pea.ai"]', timeout=10000)

        # 注册
        page.get_by_role("button", name="没有账号？去注册").click(timeout=8000)
        page.wait_for_selector('input[placeholder="可选"]', timeout=8000)
        page.fill('input[placeholder="you@pea.ai"]', EMAIL)
        page.fill('input[placeholder="至少 8 位"]', PW)
        page.fill('input[placeholder="可选"]', "验证员")
        page.locator('form button[type="submit"]').click(timeout=8000)
        page.wait_for_timeout(1500)
        token = page.evaluate("() => localStorage.getItem('pea_token') || ''") or ""
        log("token:", bool(token))

        # 启用 dev hooks 并刷新，使生产构建也暴露 window.__canvas/__ui
        page.evaluate("() => { localStorage.setItem('__peaDevHooks', '1'); }")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # 建画布
        cid = page.evaluate("""async () => {
            const r = await fetch('/canvases', {method:'POST', headers:{'content-type':'application/json','authorization':'Bearer '+localStorage.getItem('pea_token')}, body: JSON.stringify({title:'upload-verify', scope:'personal'})});
            const j = await r.json(); return j.data?.id || j.id || null;
        }""")
        log("canvas:", cid)
        page.evaluate("""(cid) => { window.__canvas.getState().openCanvas(cid); window.__ui.getState().setActive('canvas'); }""", cid)
        page.wait_for_timeout(1200)

        # 注入 AI 多图节点 + 空图片节点
        page.evaluate("""() => {
            const ai = { id:'nAi', type:'pea', position:{x:100,y:100}, data:{ kind:'image', resultUrls:['https://placehold.co/200x200/22c55e/fff?text=AI1','https://placehold.co/200x200/3b82f6/fff?text=AI2','https://placehold.co/200x200/a855f7/fff?text=AI3'], resultIndex:0, label:'AI', prompt:'ai' } };
            const up = { id:'nUp', type:'pea', position:{x:500,y:100}, data:{ kind:'image', label:'Upload' } };
            window.__canvas.getState().loadGraph([ai, up], [], 1);
        }""")
        page.wait_for_timeout(1200)

        # 统计按钮
        ai_star = page.locator(".react-flow__node[data-id='nAi'] .pea-node-result-star").count()
        ai_repl = page.locator(".react-flow__node[data-id='nAi'] .pea-node-result-replace").count()
        up_star = page.locator(".react-flow__node[data-id='nUp'] .pea-node-result-star").count()
        up_repl = page.locator(".react-flow__node[data-id='nUp'] .pea-node-result-replace").count()
        badge_count = page.locator(".react-flow__node[data-id='nAi'] .pea-node-image-badge-btn").count()
        log(f"AI图:  收藏星标={ai_star}  替换按钮={ai_repl}  多图角标={badge_count}")
        log(f"上传图: 收藏星标={up_star}  替换按钮={up_repl}")

        # 点击多图角标打开 Lightbox
        if badge_count:
            page.locator(".react-flow__node[data-id='nAi'] .pea-node-image-badge-btn").click()
            page.wait_for_timeout(600)
            lightbox_ok = page.locator(".pea-node-lightbox").count() == 1
            topbtns = page.locator(".pea-node-lightbox-topbar .pea-node-lightbox-topbtn").count()
            log("Lightbox 打开:", lightbox_ok, "顶部按钮:", topbtns)
            if lightbox_ok:
                page.locator(".pea-node-lightbox-close").click()
                page.wait_for_timeout(300)

        # 测试本地上传：点击空图片节点上传按钮
        if not os.path.exists(TEST_IMG):
            from gen_test_image import make_png
            make_png(TEST_IMG, 400, 300)

        # 触发上传节点文件选择
        with page.expect_file_chooser() as fc_info:
            page.locator(".react-flow__node[data-id='nUp'] .pea-node-media-upload").click()
        fc = fc_info.value
        fc.set_files(TEST_IMG)
        page.wait_for_timeout(2500)

        # 上传后检查节点是否有图片和替换按钮
        up_img = page.locator(".react-flow__node[data-id='nUp'] .pea-node-result-image-wrap img, .react-flow__node[data-id='nUp'] .pea-node-media-preview").count()
        up_repl = page.locator(".react-flow__node[data-id='nUp'] .pea-node-result-replace").count()
        log("上传后上传图图片元素数:", up_img)
        log("上传后上传图替换按钮:", up_repl)
        log("上传接口成功:", upload_ok)

        log("总 console error 数:", len(errs))
        for e in errs[:10]:
            log("  ERR:", e[:200])

        ok = (ai_star == 1 and ai_repl == 1 and up_star == 0 and up_repl == 1 and
              badge_count == 1 and lightbox_ok and upload_ok and up_img >= 1)
        log("验证通过" if ok else "验证失败")
        b.close()
        sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
