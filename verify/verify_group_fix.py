import time, json
from playwright.sync_api import sync_playwright

WEB = "http://localhost:5173"
EMAIL = "test@example.com"
PASSWORD = "password123"

def nav_to_canvas(page):
    if "/canvas" not in page.url:
        try:
            page.locator("text=未命名画布").first.click(timeout=6000)
        except Exception:
            page.locator("a[href*='/canvas']").first.click(timeout=6000)
    page.wait_for_selector(".react-flow__pane", timeout=30000)
    time.sleep(1)

def main():
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(f"{WEB}/login")
        page.fill("input#email, input[type='email']", EMAIL)
        page.fill("input#password, input[type='password']", PASSWORD)
        page.click("button:has-text('登 录')")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        if "/login" in page.url:
            raise RuntimeError("login failed: still on /login")
        nav_to_canvas(page)

        # fresh two nodes
        ids = page.evaluate("""() => {
            const s = window.__canvas.getState();
            return [s.addNode({ kind: 'image', label: '图片' }, { x: 400, y: 300 }),
                    s.addNode({ kind: 'text', label: '文本' }, { x: 800, y: 300 })];
        }""")
        time.sleep(0.5)
        gid = page.evaluate("""(ids) => window.__canvas.getState().groupNodes(ids)""", ids)
        time.sleep(1)
        # group is selected here (user flow: 新建组后)

        # --- Scenario 1: group selected, hover inner node ---
        pre = page.evaluate("""(a) => {
            const g = document.querySelector(`.react-flow__node[data-id="${a.gid}"]`);
            const c = document.querySelector(`.react-flow__node[data-id="${a.cid}"]`);
            const cr = c.getBoundingClientRect();
            const top = document.elementFromPoint(cr.x+cr.width/2, cr.y+cr.height/2);
            return {
                groupZ: getComputedStyle(g).zIndex,
                childZ: getComputedStyle(c).zIndex,
                groupSelected: g.classList.contains('selected'),
                topNodeAtChildCenter: top ? top.closest('.react-flow__node')?.getAttribute('data-id') : null,
            };
        }""", {"gid": gid, "cid": ids[0]})
        results["scenario1_before_hover"] = pre

        bbox = page.locator(f"[data-id='{ids[0]}']").bounding_box()
        page.mouse.move(bbox["x"]+bbox["width"]/2, bbox["y"]+bbox["height"]/2)
        time.sleep(0.6)
        s1 = page.evaluate("""(cid) => {
            const c = document.querySelector(`.react-flow__node[data-id="${cid}"]`);
            const pea = c.querySelector('.pea-node');
            const h = c.querySelector('.pea-handle');
            return { hoverClass: pea?.classList.contains('hover'), handleOpacity: h ? getComputedStyle(h).opacity : null };
        }""", ids[0])
        results["scenario1_hover"] = s1
        page.screenshot(path="D:/workspace/pea/verify/fix_group_hover.png")

        # --- Scenario 2: click inner node to select it (should select CHILD not group) ---
        page.mouse.click(bbox["x"]+bbox["width"]/2, bbox["y"]+bbox["height"]/2)
        time.sleep(0.5)
        s2 = page.evaluate("""(a) => {
            const g = document.querySelector(`.react-flow__node[data-id="${a.gid}"]`);
            const c = document.querySelector(`.react-flow__node[data-id="${a.cid}"]`);
            return { groupSelected: g.classList.contains('selected'), childSelected: c.classList.contains('selected') };
        }""", {"gid": gid, "cid": ids[0]})
        results["scenario2_click_select"] = s2

        # --- Scenario 3: functional connection drag from child1 handle to child2 handle ---
        # hover child1 to reveal handles, grab its right handle, drop on child2 left handle
        b1 = page.locator(f"[data-id='{ids[0]}']").bounding_box()
        page.mouse.move(b1["x"]+b1["width"]/2, b1["y"]+b1["height"]/2)
        time.sleep(0.4)
        # right handle is at right edge, translated out by ~9.5px at hover size; sample via DOM
        hpos = page.evaluate("""(cid) => {
            const c = document.querySelector(`.react-flow__node[data-id="${cid}"]`);
            const h = c.querySelector('.react-flow__handle-right, .pea-handle-right, .react-flow__handle[data-handlepos="right"]');
            if(!h) return null;
            const r = h.getBoundingClientRect();
            return {x: r.x+r.width/2, y: r.y+r.height/2};
        }""", ids[0])
        b2 = page.locator(f"[data-id='{ids[1]}']").bounding_box()
        tpos = page.evaluate("""(cid) => {
            const c = document.querySelector(`.react-flow__node[data-id="${cid}"]`);
            const h = c.querySelector('.react-flow__handle-left, .pea-handle-left, .react-flow__handle[data-handlepos="left"]');
            if(!h) return null;
            const r = h.getBoundingClientRect();
            return {x: r.x+r.width/2, y: r.y+r.height/2};
        }""", ids[1])
        conn_ok = None
        if hpos and tpos:
            page.mouse.move(hpos["x"], hpos["y"])
            time.sleep(0.2)
            page.mouse.down()
            page.mouse.move((hpos["x"]+tpos["x"])/2, (hpos["y"]+tpos["y"])/2, steps=8)
            page.mouse.move(tpos["x"], tpos["y"], steps=8)
            time.sleep(0.2)
            page.mouse.up()
            time.sleep(0.5)
            edges = page.evaluate("""() => window.__canvas.getState().edges.length""")
            conn_ok = edges > 0
        results["scenario3_connection"] = {"handlePosFound": bool(hpos and tpos), "edgeCreated": conn_ok}

        print(json.dumps(results, ensure_ascii=False, indent=2))
        browser.close()

if __name__ == "__main__":
    main()
