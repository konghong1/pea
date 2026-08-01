"""验证媒体节点有上游输入时隐藏上传按钮

修复点：视频/音频节点在有输入节点时，顶部上传入口应像图片节点一样隐藏，
因为内容将由上游节点提供。

测试策略：通过 dev hooks 直接操作 canvas store 创建节点/连线，
检查 DOM 中 .pea-node-upload-btn 的数量变化。
"""
import os, sys, uuid, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
EMAIL = f"uhide_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"


def main():
    errors = []
    def step(label, ok, detail=""):
        icon = "PASS" if ok else "FAIL"
        print(f"[{icon}] {label}  {detail}")
        if not ok: errors.append(label)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error", "warn") else None)
        page.on("pageerror", lambda e: print("[pageerror]", e))

        def open_canvas(cid):
            page.evaluate(f"""() => window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))""")
            page.wait_for_selector(".react-flow__viewport", timeout=20000)
            page.wait_for_timeout(700)

        def upload_btn_count():
            return page.evaluate("""() => document.querySelectorAll('.pea-node-upload-btn').length""")

        # ========== 注册并进入画布 ==========
        page.goto(BASE, wait_until="domcontentloaded"); page.wait_for_timeout(600)
        page.evaluate("localStorage.setItem('__peaDevHooks','1')")
        page.reload(wait_until="domcontentloaded"); page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click(); page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', EMAIL)
        page.fill('input[placeholder="至少 8 位"]', PW)
        page.fill('input[placeholder="可选"]', "UHIDE")
        page.locator("form button[type=submit]").click(); page.wait_for_timeout(3500)
        page.wait_for_selector("text=新建项目", timeout=8000)
        page.locator("text=新建项目").first.click(); page.wait_for_timeout(1000)
        page.wait_for_selector(".react-flow__viewport", timeout=20000)
        page.wait_for_timeout(800)

        cid = page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'upload-hide',scope:'personal'})});
            return (await r.json()).id;
        }""")
        open_canvas(cid)

        # ========== 1) 无输入时三个媒体节点都显示上传按钮 ==========
        print("\n--- Test 1: media nodes without upstream inputs show upload button ---")
        page.evaluate("""() => {
            const s = window.__canvas.getState();
            const mk = (id, kind, x, y, extra={}) => ({id, type:'pea', position:{x,y}, data:{kind, label:kind, aspectRatio:'16:9', ...extra}});
            s.loadGraph([
                mk('nImg','image',200,200),
                mk('nVid','video',600,200),
                mk('nAud','audio',1000,200),
            ], [], s.version);
        }""")
        page.wait_for_timeout(800)
        c1 = upload_btn_count()
        step("无输入时图片/视频/音频均显示上传按钮", c1 == 3, f"upload_btn_count={c1}")

        # ========== 2) 添加输入后边后上传按钮全部隐藏 ==========
        print("\n--- Test 2: media nodes with upstream inputs hide upload button ---")
        page.evaluate("""() => {
            const s = window.__canvas.getState();
            const mk = (id, kind, x, y, extra={}) => ({id, type:'pea', position:{x,y}, data:{kind, label:kind, aspectRatio:'16:9', ...extra}});
            const src = mk('nSrc','generate',100,500,{prompt:'source'});
            s.loadGraph([
                mk('nImg','image',200,200),
                mk('nVid','video',600,200),
                mk('nAud','audio',1000,200),
                src,
            ], [
                {id:'eImg', source:'nSrc', target:'nImg', type:'pea'},
                {id:'eVid', source:'nSrc', target:'nVid', type:'pea'},
                {id:'eAud', source:'nSrc', target:'nAud', type:'pea'},
            ], s.version);
        }""")
        page.wait_for_timeout(800)
        c2 = upload_btn_count()
        step("有输入时图片/视频/音频均隐藏上传按钮", c2 == 0, f"upload_btn_count={c2}")

        # ========== 3) 删除输入边后上传按钮恢复 ==========
        print("\n--- Test 3: removing upstream inputs restores upload button ---")
        page.evaluate("""() => {
            const s = window.__canvas.getState();
            s.removeEdge('eImg');
            s.removeEdge('eVid');
            s.removeEdge('eAud');
        }""")
        page.wait_for_timeout(800)
        c3 = upload_btn_count()
        step("删除输入边后上传按钮恢复显示", c3 == 3, f"upload_btn_count={c3}")

        # 截图
        shots = os.path.dirname(__file__) + '/shots'
        os.makedirs(shots, exist_ok=True)
        page.screenshot(path=f'{shots}/media_upload_hide_on_input.png')
        print(f"\n截图保存: {shots}/media_upload_hide_on_input.png")

        browser.close()

        if errors:
            print(f"\n❌ 共 {len(errors)} 项失败: {errors}")
            sys.exit(1)
        else:
            print("\n✅ 媒体节点有输入时隐藏上传按钮全部通过!")


if __name__ == '__main__':
    main()
