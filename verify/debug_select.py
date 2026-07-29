"""Diagnose why box-select selects 0 nodes. Tries plain-drag and shift-drag."""
import time, random, string
BASE = "http://localhost:8088"

def rand_email():
    return f"dbg_{''.join(random.choices(string.ascii_lowercase, k=5))}_{int(time.time())}@test.pea"

def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.add_init_script("localStorage.setItem('__peaDevHooks','1')")
        pg.set_default_timeout(10000)

        pg.goto(f"{BASE}/login", wait_until="domcontentloaded"); pg.wait_for_timeout(800)
        rb = pg.query_selector('button:has-text("去注册"), button:has-text("没有账号")')
        if rb: rb.click(); pg.wait_for_timeout(400)
        email = rand_email(); pw = "Test12345678"
        pg.fill('#email', email); pg.fill('#password', pw)
        ni = pg.query_selector('input[placeholder="可选"]')
        if ni: ni.fill("DBG")
        sb = pg.query_selector('button[type="submit"]')
        if sb: sb.click(); pg.wait_for_timeout(2500)
        if "/login" in pg.url:
            pg.fill('#email', email); pg.fill('#password', pw)
            sb = pg.query_selector('button[type="submit"]'); sb.click(); pg.wait_for_timeout(2500)
        print("logged in. url=", pg.url)

        pg.wait_for_timeout(1000)
        # enter canvas
        if not pg.query_selector(".react-flow"):
            for btn in pg.query_selector_all('button:has-text("新建"), a:has-text("新建")'):
                try:
                    btn.click(); pg.wait_for_timeout(1500)
                    if pg.query_selector(".react-flow"): break
                except Exception: pass
        print("in canvas:", bool(pg.query_selector(".react-flow")))

        # ensure hook
        hook = pg.evaluate("() => !!(window.__canvas && window.__canvas.getState)")
        print("hook:", hook)
        pg.evaluate("""() => { const s=window.__canvas.getState(); if(!s.canvasId) s.setCanvasMeta(999999,1,'DBG'); }""")

        created = pg.evaluate("""() => {
            const s = window.__canvas.getState();
            const a = s.addNode({label:'A',kind:'image'},{x:120,y:100});
            const b = s.addNode({label:'B',kind:'image'},{x:470,y:400});
            return [a,b];
        }""")
        pg.wait_for_timeout(1200)
        print("created:", created)

        pane = pg.query_selector(".react-flow__pane")
        pr = pane.bounding_box()
        print("pane box:", pr)

        rects = pg.evaluate("""() => {
            const ns = Array.from(document.querySelectorAll('.react-flow__node[data-id]'));
            let mx=Infinity,my=Infinity,Mx=-Infinity,My=-Infinity;
            ns.forEach(n=>{const r=n.getBoundingClientRect();mx=Math.min(mx,r.left);my=Math.min(my,r.top);Mx=Math.max(Mx,r.right);My=Math.max(My,r.bottom);});
            return {count:ns.length, mx,my,Mx,My,
              nodes: ns.map(n=>{const r=n.getBoundingClientRect();return {id:n.getAttribute('data-id'),l:r.left,t:r.top,r:r.right,b:r.bottom};})};
        }""")
        print("rects:", rects)

        sx, sy = rects["mx"]-30, rects["my"]-30
        ex, ey = rects["Mx"]+30, rects["My"]+30
        print("drag from", (round(sx),round(sy)), "to", (round(ex),round(ey)))
        # is start inside pane?
        inside = (pr["x"] <= sx <= pr["x"]+pr["width"]) and (pr["y"] <= sy <= pr["y"]+pr["height"])
        print("start inside pane:", inside)

        def try_drag(use_shift):
            if use_shift: pg.keyboard.down("Shift")
            pg.mouse.move(sx, sy); pg.mouse.down()
            for i in range(1,13):
                pg.mouse.move(sx+(ex-sx)*i/12, sy+(ey-sy)*i/12); pg.wait_for_timeout(35)
            pg.mouse.up()
            if use_shift: pg.keyboard.up("Shift")
            pg.wait_for_timeout(1000)
            st = pg.evaluate("""() => ({
                sel: document.querySelectorAll('.react-flow__node.selected').length,
                rect: !!document.querySelector('.react-flow__nodesselection-rect'),
                rectFill: (()=>{const e=document.querySelector('.react-flow__nodesselection-rect');return e?getComputedStyle(e).fill:null;})()
            })""")
            print(f"  [shift={use_shift}] ->", st)
            return st["sel"]

        sel1 = try_drag(False)
        if sel1 < 2:
            pg.screenshot(path="debug_select_plain.png")
            sel2 = try_drag(True)
            if sel2 < 2:
                pg.screenshot(path="debug_select_shift.png")
                # dump computed selectedIds
                dump = pg.evaluate("""() => {
                    const s = window.__canvas.getState();
                    return { selectedIds: s.selectedIds, nodesSelected: s.nodes.filter(n=>n.selected).map(n=>n.id) };
                }""")
                print("store dump:", dump)
        print("DONE sel1=", sel1)
        b.close()

if __name__ == "__main__":
    main()
