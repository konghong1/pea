"""验证：画布左侧工具栏图标已替换为统一 antd SVG 图标，无 emoji。

运行：python verify_toolbar_icons.py
"""
import sys, uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
EMAIL = f"dbg_tlb_{uuid.uuid4().hex[:8]}@pea.dev"
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

    try:
        pg.click("text=去注册", timeout=5000)
        pg.wait_for_timeout(300)
    except Exception:
        pass
    pg.fill('input[placeholder="you@pea.ai"]', EMAIL)
    pg.fill('input[placeholder="至少 8 位"]', PW)
    pg.fill('input[placeholder="可选"]', "TlbBot")
    pg.locator("form button[type=submit]").click()
    pg.wait_for_timeout(4000)

    cid = pg.evaluate("""async () => {
        const token = localStorage.getItem('pea_token');
        const r = await fetch('/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'tlb-dbg',scope:'personal'})});
        return (await r.json()).id;
    }""")
    pg.evaluate(f"window.__canvas.getState().openCanvas({cid!r}).then(() => window.__ui.getState().setActive('canvas'))")
    pg.wait_for_selector(".pea-toolbar", timeout=20000)
    pg.wait_for_timeout(800)

    # 截图工具栏区域
    toolbar = pg.locator(".pea-toolbar")
    box = toolbar.bounding_box()
    SHOTS = r"C:\workspace\pea\verify\shots"
    import os
    os.makedirs(SHOTS, exist_ok=True)
    shot_path = os.path.join(SHOTS, "toolbar_after.png")
    pg.screenshot(path=shot_path, clip={"x": int(box["x"] - 10), "y": int(box["y"] - 10), "width": int(box["width"] + 20), "height": int(box["height"] + 20)})
    print(f"[info] screenshot saved: {shot_path}", flush=True)

    state = pg.evaluate(r"""() => {
        const btns = [...document.querySelectorAll('.pea-tlb-btn')];
        const avatar = document.querySelector('.pea-tlb-avatar');
        return {
            btnCount: btns.length,
            svgCount: btns.filter(b => b.querySelector('svg')).length,
            emojiCount: btns.filter(b => /[\u{1F300}-\u{1F9FF}]/u.test(b.textContent || '')).length,
            hasActiveClass: document.querySelector('.pea-tlb-btn.active') !== null,
            avatarHasBrandGradient: window.getComputedStyle(avatar).backgroundImage.includes('linear-gradient'),
        };
    }""")
    print(f"[info] toolbar state: {state}", flush=True)

    check("工具栏有 6 个功能按钮", state["btnCount"] == 6, f"count={state['btnCount']}")
    check("所有按钮使用 SVG 图标", state["svgCount"] == state["btnCount"], f"svg={state['svgCount']}")
    check("无 emoji 字符", state["emojiCount"] == 0, f"emoji={state['emojiCount']}")
    check("头像保留品牌渐变", state["avatarHasBrandGradient"], f"bg={state['avatarHasBrandGradient']}")

    # 验证 active 状态与面板开关联动：点「添加节点」后该按钮应高亮
    pg.locator(".pea-tlb-btn").first.click()
    pg.wait_for_timeout(400)
    active = pg.evaluate("() => document.querySelectorAll('.pea-tlb-btn.active').length")
    check("点击后按钮进入 active 高亮状态", active >= 1, f"activeCount={active}")

    check("无 console / page 错误", len(errs) == 0, f"errs={errs[:3]}")

    b.close()

print("\n==== RESULT ====", "ALL PASS" if not fails else f"FAILED: {fails}", flush=True)
sys.exit(1 if fails else 0)
