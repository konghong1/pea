from playwright.sync_api import sync_playwright
import time, sys

BASE = "http://localhost:8088"

def log(*a): print(*a, flush=True)

def full_token(page):
    return page.evaluate("() => localStorage.getItem('pea_token')")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errs = []
    page.on("console", lambda m: m.type == "error" and errs.append(m.text))
    page.on("pageerror", lambda e: errs.append(str(e)))

    # 1) 注册登录
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    ts = int(time.time() * 1000)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(400)
    page.fill('input[placeholder="you@pea.ai"]', f"rr_{ts}@pea.ai")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(8000)
    tok_login = full_token(page)
    log("[1] 登录后 token 前8:", (tok_login or "")[:8])

    # 2) 新建项目 -> 创建并打开画布
    page.locator("button:has-text('新建项目')").first.click()
    page.wait_for_timeout(6000)
    vp = page.locator(".react-flow__viewport").count()
    route = page.evaluate("() => localStorage.getItem('pea_ui_route')")
    log(f"[2] 画布视口数={vp} | pea_ui_route={route}")

    # 3) 硬刷：应回到画布（不丢位置、不被踢登录）
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    vp2 = page.locator(".react-flow__viewport").count()
    url2 = page.url
    tok_after = full_token(page)
    log(f"[3] 硬刷后 画布视口数={vp2} | url={url2} | 被踢登录?={('/login' in url2)} | token 存活={bool(tok_after)}")
    log(f"    续期前(登录)token前8={ (tok_login or '')[:8] } | 硬刷后token前8={ (tok_after or '')[:8] }")

    # 4) 直接验 /auth/refresh 端点（完整 token 比对）
    refresh_out = page.evaluate("""async () => {
        const tok = localStorage.getItem('pea_token');
        const r = await fetch('/auth/refresh', {method:'POST', headers:{'Authorization':'Bearer '+tok}});
        const j = await r.json().catch(()=>null);
        return {status:r.status, newTok:(j&&j.token)||null};
    }""")
    log(f"[4] /auth/refresh: status={refresh_out.get('status')} 返回新token?={bool(refresh_out.get('newTok'))}")
    if refresh_out.get("newTok"):
        log(f"    新token前8={refresh_out['newTok'][:8]} 与登录token不同?={refresh_out['newTok']!=tok_login}")

    # 5) 验证前端 boot 续期：app 启动(refreshMe->refreshToken)后 localStorage token 应已被换新（与登录时不同）
    log(f"[5] 前端 boot 续期生效? (硬刷后 token != 登录时 token): {tok_after != tok_login}")

    log("=== console errors ===", errs[:6])
    browser.close()
