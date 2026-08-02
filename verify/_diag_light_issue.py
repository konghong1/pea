"""Diagnose light-theme visibility of TopNav balance button + node generate button."""
import uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"

def run(theme):
    out_top = f"verify/_diag_{theme}_topnav.png"
    out_launch = f"verify/_diag_{theme}_launcher.png"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        ctx = browser.new_context(viewport={"width":1440,"height":900}, device_scale_factor=2)
        page = ctx.new_page()
        page.on("console", lambda m: print(f"[{theme}|c:{m.type}] {m.text}") if m.type in ("error","warning") else None)
        page.add_init_script(f"localStorage.setItem('pea_theme','{theme}')")
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        try:
            page.locator("text=没有账号？去注册").first.click(timeout=4000)
            page.wait_for_timeout(400)
            email = f"dbg_{uuid.uuid4().hex[:8]}@pea.ai"
            page.fill('input[placeholder="you@pea.ai"]', email)
            page.fill('input[placeholder="至少 8 位"]', "test1234")
            page.fill('input[placeholder="可选"]', "Dbg")
            page.locator("form button[type=submit]").click()
            page.wait_for_timeout(2000)
            page.wait_for_selector("text=新建项目", timeout=15000)
        except Exception as e:
            print(f"[{theme}|register] skipped: {e}")

        cid = page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'dbg',scope:'personal'})});
            return (await r.json()).id;
        }""")
        print(f"[{theme}] cid:", cid)
        page.goto(f"{BASE}/workspace", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        try:
            page.locator(f'[data-canvas-id="{cid}"]').first.click(timeout=8000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[{theme}|open] {e}")

        isdark = page.evaluate("() => document.documentElement.classList.contains('dark')")
        print(f"[{theme}] html.dark = {isdark}; url={page.url}")

        # ---- TopNav balance button: find by text 'Tapies' anywhere ----
        bal = page.evaluate("""() => {
            const els = [...document.querySelectorAll('button, a, span')];
            const b = els.find(x => /Tapies/.test(x.textContent) && x.children.length<=2 && x.getBoundingClientRect().width>0);
            if(!b) return {found:false};
            const cs = getComputedStyle(b);
            const r = b.getBoundingClientRect();
            const icon = b.querySelector('.anticon-wallet, svg');
            return {
                found:true, tag:b.tagName, cls:b.className.toString().slice(0,60),
                text: b.textContent.trim().slice(0,40),
                rect:{x:r.x,y:r.y,w:r.width,h:r.height},
                bg: cs.backgroundColor, color: cs.color, border: cs.borderTopWidth+' '+cs.borderTopColor,
                hasWallet: !!b.querySelector('.anticon-wallet'),
                parentCls: b.parentElement? b.parentElement.className.toString().slice(0,60): null
            };
        }""")
        print(f"[{theme}|topnav-balance] {bal}")
        if bal.get('found') and bal.get('rect',{}).get('w'):
            r = bal['rect']
            page.screenshot(path=out_top, clip={"x":max(0,r['x']-10),"y":max(0,r['y']-10),"width":r['w']+20,"height":r['h']+20})
        else:
            # fallback: screenshot top strip of viewport
            page.screenshot(path=out_top, clip={"x":0,"y":0,"width":1440,"height":52})

        # ---- node launcher ----
        if not page.evaluate("() => document.querySelectorAll('.react-flow__node').length"):
            pane = page.locator(".react-flow__pane").first
            bb = pane.bounding_box()
            page.mouse.dblclick(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2)
            page.wait_for_timeout(800)
            page.locator(".pea-add-menu-item", has_text="图片").first.click(timeout=6000)
            page.wait_for_timeout(1500)
        try:
            page.locator(".pe-launcher").first.wait_for(state="visible", timeout=12000)
        except Exception as e:
            print(f"[{theme}] launcher not visible: {e}")
        lb = page.locator(".pe-launcher").first.bounding_box()
        if lb:
            page.screenshot(path=out_launch, clip={"x":max(0,lb['x']-24),"y":max(0,lb['y']-60),"width":lb['width']+48,"height":lb['height']+120})
            linfo = page.evaluate("""() => {
                const l = document.querySelector('.pe-launcher');
                if(!l) return {found:false};
                const cs = getComputedStyle(l);
                const num = l.querySelector('.pe-cost-num');
                const bar = document.querySelector('.node-input-bar');
                const bcs = bar? getComputedStyle(bar): null;
                return {
                    found:true,
                    launcherBg: cs.backgroundColor + ' / ' + cs.backgroundImage.slice(0,40),
                    launcherColor: cs.color,
                    costNumColor: num? getComputedStyle(num).color : null,
                    barBg: bcs? bcs.backgroundColor + ' / ' + bcs.backgroundImage.slice(0,30) : null,
                    barColor: bcs? bcs.color : null,
                };
            }""")
            print(f"[{theme}|launcher] {linfo}")
        browser.close()

run("light")
run("dark")
print("\nDone.")
