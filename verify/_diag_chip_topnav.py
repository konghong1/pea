"""Capture canvas balance chip + home page TopNav in both themes."""
import uuid
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"

def run(theme):
    out_chip = f"verify/_diag_{theme}_chip.png"
    out_home = f"verify/_diag_{theme}_home.png"
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
            print(f"[{theme}|reg] skipped: {e}")

        # ---- Home page TopNav ----
        print(f"[{theme}] url={page.url}")
        page.screenshot(path=out_home, clip={"x":0,"y":0,"width":1440,"height":56})
        # find any element containing 'Tapies' on home
        hinfo = page.evaluate("""() => {
            const all = [...document.querySelectorAll('*')];
            const t = all.find(x => /Tapies/.test(x.textContent) && x.getBoundingClientRect().width>0);
            if(!t) return {found:false};
            const cs = getComputedStyle(t), r=t.getBoundingClientRect();
            return {found:true, tag:t.tagName, cls:t.className.toString().slice(0,60),
                text:t.textContent.trim().slice(0,40),
                bg:cs.backgroundColor, color:cs.color,
                rect:{x:r.x,y:r.y,w:r.width,h:r.height},
                hasWallet:!!t.querySelector('.anticon-wallet')};
        }""")
        print(f"[{theme}|home-tapies] {hinfo}")

        # ---- Canvas editor: open a project, then screenshot chip ----
        cid = page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/api/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'dbg2',scope:'personal'})});
            return (await r.json()).id;
        }""")
        print(f"[{theme}] cid:", cid)
        page.goto(f"{BASE}/workspace", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        try:
            page.locator(f'[data-canvas-id="{cid}"]').first.click(timeout=8000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[{theme}|open] {e}")

        # find .pea-canvas-tapies or any balance display
        cinfo = page.evaluate("""() => {
            const chip = document.querySelector('.pea-canvas-tapies');
            if(chip) {
                const cs=getComputedStyle(chip), r=chip.getBoundingClientRect();
                const num=chip.querySelector('.pea-balance-num');
                const gem=chip.querySelector('.pea-balance-gem');
                return {
                    found:true, text:chip.textContent.trim().slice(0,30),
                    bg:cs.backgroundColor+' / '+cs.backgroundImage.slice(0,50),
                    color:cs.color, border:cs.borderTopWidth+' '+cs.borderTopColor,
                    numText:num?num.textContent:null,
                    numColor:num?getComputedStyle(num).color:null,
                    rect:{x:r.x,y:r.y,w:r.width,h:r.height},
                    hasGem:!!gem
                };
            }
            // fallback: search for any balance-like element
            const all=[...document.querySelectorAll('[class*="tapies"], [class*="balance"], [class*="wallet"]')];
            return {found:false, candidates:all.map(e=>e.className.toString().slice(0,40))};
        }""")
        print(f"[{theme}|canvas-chip] {cinfo}")
        if cinfo.get('found'):
            r=cinfo['rect']
            page.screenshot(path=out_chip, clip={"x":max(0,r['x']-12),"y":max(0,r['y']-12),"width":r['w']+24,"height":r['h']+24})
        browser.close()

run("light")
run("dark")
print("\nDone.")
