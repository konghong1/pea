"""验证：出图数量下拉框点击后不再飞出页面。

复现用户场景：进入画布 -> 选中一个图片节点 -> 点击「生成数量」按钮 ->
检查下拉弹窗出现在视口内、且多帧保持稳定(无反馈fly-off) -> 选择选项后正确回填并关闭。

运行：python verify_count_dropdown.py   (需要 8088 已在跑、Chromium 已装)
"""
import sys, time, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
EMAIL = f"dbg_count_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"

fails = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""), flush=True)
    if not cond:
        fails.append(name)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('__peaDevHooks','1');}catch(e){} window.__peaDevHooks='1';")
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append("PAGEERR:" + str(e)))

    pg.goto(BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(800)

    # 注册
    try:
        pg.click("text=去注册", timeout=5000)
        pg.wait_for_timeout(300)
    except Exception:
        pass
    pg.fill('input[placeholder="you@pea.ai"]', EMAIL)
    pg.fill('input[placeholder="至少 8 位"]', PW)
    pg.fill('input[placeholder="可选"]', "CntBot")
    pg.locator("form button[type=submit]").click()
    pg.wait_for_timeout(4000)

    # 新建画布
    cid = pg.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'count-dbg',scope:'personal'})});
        return (await r.json()).id;
    }""")
    pg.evaluate(f"window.__canvas.getState().openCanvas({cid!r}).then(() => window.__ui.getState().setActive('canvas'))")
    pg.wait_for_selector(".react-flow__viewport", timeout=20000)
    pg.wait_for_timeout(1000)

    # 注入一个图片(生成结果)节点并选中
    pg.evaluate("""() => {
        const s = window.__canvas.getState();
        const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
        const img = mk('nImg','image',300,300,{resultUrl:'https://placehold.co/120x120/1fa2dc/ffffff?text=Ref',meta:{fileName:'a.png'}});
        s.loadGraph([img],[],s.version);
        s.select('nImg');
        return true;
    }""")
    pg.wait_for_selector(".node-count-btn", timeout=10000)
    pg.wait_for_timeout(500)

    # 记录触发按钮位置
    btn = pg.locator(".node-count-btn")
    btn_box = btn.bounding_box()
    print(f"[info] count button box: {btn_box}", flush=True)

    # 点击打开下拉
    btn.click()
    pg.wait_for_selector(".node-count-btn-dropdown", timeout=5000)
    pg.wait_for_timeout(300)

    def dropdown_rect():
        return pg.evaluate("""() => {
            const el = document.querySelector('.node-count-btn-dropdown');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {left:r.left, top:r.top, right:r.right, bottom:r.bottom, w:r.width, h:r.height};
        }""")

    ih = pg.evaluate("window.innerHeight")
    iw = pg.evaluate("window.innerWidth")

    # 多帧采样，检测是否 fly-off（反馈循环会让 bottom 持续增大）
    samples = []
    for _ in range(4):
        samples.append(dropdown_rect())
        pg.wait_for_timeout(150)
    print(f"[info] dropdown rect samples: {samples}", flush=True)

    r0 = samples[0]
    check("下拉已出现且在视口内(左>=0)", r0["left"] >= -1, f"left={r0['left']:.1f}")
    check("下拉已出现且在视口内(右<=vw)", r0["right"] <= iw + 1, f"right={r0['right']:.1f} vw={iw}")
    check("下拉已出现且在视口内(顶>=0)", r0["top"] >= -1, f"top={r0['top']:.1f}")
    check("下拉已出现且在视口内(底<=vh)", r0["bottom"] <= ih + 1, f"bottom={r0['bottom']:.1f} vh={ih}")

    # 稳定性：不应每帧持续下移（旧 bug 每帧 bottom+10px）
    bottoms = [s["bottom"] for s in samples]
    drift = max(bottoms) - min(bottoms)
    check("多帧稳定无 fly-off(底部位移<30px)", drift < 30, f"drift={drift:.1f}px")

    # 逻辑位置：弹窗底边应在按钮底边上方(gap≈10)，即 dropdown.bottom ≈ button.bottom - 10
    expect_bottom = btn_box["y"] + btn_box["height"] - 10
    check("弹窗贴合按钮上方(底边≈按钮底-10)", abs(r0["bottom"] - expect_bottom) < 40,
          f"dd.bottom={r0['bottom']:.1f} expect≈{expect_bottom:.1f}")

    # 选择一个选项(4x) -> 回填 + 关闭
    pg.locator(".node-count-opt", has_text="4x").click()
    pg.wait_for_timeout(400)
    closed = pg.evaluate("() => !document.querySelector('.node-count-btn-dropdown')")
    check("选择后下拉已关闭", closed)
    txt = pg.locator(".node-count-btn").inner_text()
    check("数量回填为 4x", "4x" in txt, f"btn_text={txt!r}")

    check("无 console / page 错误", len(errs) == 0, f"errs={errs[:3]}")

    b.close()

print("\n==== RESULT ====", "ALL PASS" if not fails else f"FAILED: {fails}", flush=True)
sys.exit(1 if fails else 0)
