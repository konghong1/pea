import time, json
from playwright.sync_api import sync_playwright

WEB = "http://localhost:5173"
EMAIL = "test@example.com"
PASSWORD = "password123"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width":1440,"height":900}).new_page()
    page.goto(f"{WEB}/login")
    page.fill("input#email, input[type='email']", EMAIL)
    page.fill("input#password, input[type='password']", PASSWORD)
    page.click("button:has-text('登 录')")
    page.wait_for_load_state("networkidle"); time.sleep(1)
    if "/canvas" not in page.url:
        page.locator("text=未命名画布").first.click(timeout=6000)
    page.wait_for_selector(".react-flow__pane", timeout=30000); time.sleep(1)

    ids = page.evaluate("""() => { const s=window.__canvas.getState();
        return [s.addNode({kind:'image',label:'图片'},{x:400,y:300}), s.addNode({kind:'text',label:'文本'},{x:800,y:300})]; }""")
    time.sleep(0.4)
    gid = page.evaluate("""(ids)=>window.__canvas.getState().groupNodes(ids)""", ids)
    time.sleep(1)

    def hover_check():
        bbox = page.locator(f"[data-id='{ids[0]}']").bounding_box()
        page.mouse.move(bbox["x"]+bbox["width"]/2, bbox["y"]+bbox["height"]/2)
        time.sleep(0.5)
        return page.evaluate("""(cid) => {
            const c = document.querySelector(`.react-flow__node[data-id="${cid}"]`);
            const pea = c.querySelector('.pea-node'); const h = c.querySelector('.pea-handle');
            const r = c.getBoundingClientRect();
            const top = document.elementFromPoint(r.x+r.width/2, r.y+r.height/2);
            return { hover: pea?.classList.contains('hover'), handleOpacity: h?getComputedStyle(h).opacity:null,
                     topNode: top?top.closest('.react-flow__node')?.getAttribute('data-id'):null };
        }""", ids[0])

    # (A) With the FIX active: group forced to z:0 -> child should be top, handles visible
    before = hover_check()

    # (B) Inject a higher-specificity rule to SIMULATE the broken state (group above children)
    page.add_style_tag(content="""
        .react-flow__node.react-flow__node-group.selected.react-flow__node { z-index: 9999 !important; }
    """)
    time.sleep(0.3)
    # re-hover after forcing group on top
    page.mouse.move(10,10); time.sleep(0.2)
    broken = hover_check()

    # (C) Remove injected rule -> FIX restored -> handles visible again
    page.evaluate("""() => {
        const ss = [...document.styleSheets];
        for (const s of ss) { try {
            const rules = [...s.cssRules];
            for (const r of rules) if (r.cssText && r.cssText.includes('9999')) s.deleteRule(r);
        } catch(e){} }
    }""")
    time.sleep(0.3)
    page.mouse.move(10,10); time.sleep(0.2)
    restored = hover_check()

    print(json.dumps({"FIX_active(before)": before, "SIMULATED_BROKEN(group_on_top)": broken, "FIX_restored(after)": restored}, ensure_ascii=False, indent=2))
    browser.close()
