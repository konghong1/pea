"""Verify all 3 fixes: TopNav gem icon, chip text, launcher theme-awareness."""
import uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"

def screenshot(page, selector, out_path, pad=12):
    """Screenshot a single element by selector."""
    el = page.locator(selector).first
    try:
        el.wait_for(state="visible", timeout=8000)
        box = el.bounding_box()
        if box:
            page.screenshot(path=out_path, clip={
                "x": max(0, box["x"] - pad), "y": max(0, box["y"] - pad),
                "width": box["width"] + pad * 2, "height": box["height"] + pad * 2
            })
            return True
    except Exception as e:
        print(f"  [screenshot] {selector} failed: {e}")
    return False

def run(theme):
    tag = theme
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        ctx = browser.new_context(viewport={"width":1440,"height":900}, device_scale_factor=2)
        page = ctx.new_page()
        page.on("console", lambda m: print(f"[{tag}|c:{m.type}] {m.text}") if m.type in ("error","warning") else None)
        page.add_init_script(f"localStorage.setItem('pea_theme','{theme}')")
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # login
        try:
            page.locator("text=没有账号？去注册").first.click(timeout=4000)
            page.wait_for_timeout(400)
            email = f"v_{uuid.uuid4().hex[:8]}@pea.ai"
            page.fill('input[placeholder="you@pea.ai"]', email)
            page.fill('input[placeholder="至少 8 位"]', "test1234")
            page.fill('input[placeholder="可选"]', "V")
            page.locator("form button[type=submit]").click()
            page.wait_for_timeout(2000)
            page.wait_for_selector("text=新建项目", timeout=15000)
        except Exception as e:
            print(f"[{tag}|reg] skipped: {e}")

        isdark = page.evaluate("() => document.documentElement.classList.contains('dark')")
        print(f"[{tag}] html.dark={isdark}")

        # ---- 1) Home TopNav balance (new gem icon) ----
        ok = screenshot(page, ".pea-topnav-balance", f"verify/shot_{tag}_topnav_balance.png")
        print(f"[{tag}] topnav-balance: {'OK' if ok else 'MISSING'}")
        if ok:
            info = page.evaluate("""() => {
                const b = document.querySelector('.pea-topnav-balance');
                if(!b) return {};
                const cs=getComputedStyle(b);
                const gem=b.querySelector('.pea-balance-gem');
                const wallet=b.querySelector('.anticon-wallet');
                const num=b.querySelector('.pea-balance-num');
                return {
                    text:b.textContent.trim().slice(0,30),
                    bg:cs.backgroundColor.slice(0,20),
                    color:cs.color,
                    hasGem:!!gem,
                    hasWallet:!!wallet,
                    numText:num?num.textContent:null,
                    numColor:num?getComputedStyle(num).color:null,
                };
            }""")
            print(f"[{tag}] topnav-info: {info}")

        # ---- 2) Canvas chip ----
        cid = page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'verify',scope:'personal'})});
            return (await r.json()).id;
        }""")
        print(f"[{tag}] cid:", cid)
        page.goto(f"{BASE}/workspace", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        try:
            page.locator(f'[data-canvas-id="{cid}"]').first.click(timeout=8000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[{tag}|open] {e}")

        ok = screenshot(page, ".pea-canvas-tapies", f"verify/shot_{tag}_canvas_chip.png")
        print(f"[{tag}] canvas-chip: {'OK' if ok else 'MISSING'}")
        if ok:
            cinfo = page.evaluate("""() => {
                const c=document.querySelector('.pea-canvas-tapies');
                if(!c) return {};
                const cs=getComputedStyle(c);
                const num=c.querySelector('.pea-balance-num');
                return {
                    text:c.textContent.trim(),
                    color:cs.color,
                    numColor:num?getComputedStyle(num).color:null,
                };
            }""")
            print(f"[{tag}] chip-info: {cinfo}")

        # ---- 3) Node launcher ----
        if not page.evaluate("() => document.querySelectorAll('.react-flow__node').length"):
            pane = page.locator(".react-flow__pane").first
            bb = pane.bounding_box()
            page.mouse.dblclick(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2)
            page.wait_for_timeout(800)
            page.locator(".pea-add-menu-item", has_text="图片").first.click(timeout=6000)
            page.wait_for_timeout(1500)

        ok = screenshot(page, ".pe-launcher", f"verify/shot_{tag}_launcher.png", pad=24)
        print(f"[{tag}] launcher: {'OK' if ok else 'MISSING'}")
        if ok:
            linfo = page.evaluate("""() => {
                const l=document.querySelector('.pe-launcher');
                if(!l) return {};
                const cs=getComputedStyle(l);
                const bar=document.querySelector('.node-input-bar');
                const bcs=bar?getComputedStyle(bar):null;
                const num=l.querySelector('.pe-cost-num');
                return {
                    launcherBg:cs.backgroundColor.slice(0,18)+' / '+cs.backgroundImage.slice(0,35),
                    barBg:bcs?bcs.backgroundColor.slice(0,18):null,
                    barColor:bcs?bcs.color:null,
                    costNumColor:num?getComputedStyle(num).color:null,
                };
            }""")
            print(f"[{tag}] launcher-info: {linfo}")

        # Also capture input bar context
        bar_ok = screenshot(page, ".node-input-bar", f"verify/shot_{tag}_input_bar.png", pad=16)
        print(f"[{tag}] input-bar: {'OK' if bar_ok else 'MISSING'}")

        browser.close()

run("light")
run("dark")
print("\n✅ Verification complete.")
