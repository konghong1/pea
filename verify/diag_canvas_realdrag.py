"""诊断：真实鼠标拖动节点后，多次进入画布，节点位置/内容是否稳定。
用 Playwright 真实 mouse 拖拽 .react-flow__node，覆盖 store-action 模拟未覆盖的真实拖动路径。
"""
import os, sys, time, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
def log(*a): print("[diag_drag]", *a, flush=True)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        pg = ctx.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(BASE, wait_until="networkidle"); pg.wait_for_timeout(400)
        try: pg.click("text=去注册", timeout=4000)
        except: pass
        pg.wait_for_timeout(300)
        pg.fill("input:visible >> nth=0", "tdrag_%d@pea.ai" % int(time.time()))
        pg.fill("input:visible >> nth=1", "Passw0rd!")
        try: pg.click("button:has-text('注')", timeout=4000)
        except: pass
        pg.wait_for_timeout(800)
        try: pg.click("text=新建项目", timeout=4000)
        except: pass
        pg.wait_for_timeout(1000)

        C = pg.evaluate("window.__canvas.getState().canvasId")
        pg.evaluate("window.__canvas.getState().addNode({ kind:'text', label:'Drag', meta:{} }, { x:120, y:120 })")
        pg.wait_for_timeout(500)
        nid = pg.evaluate("window.__canvas.getState().nodes[0].id")

        def read():
            return pg.evaluate("""(id) => {
              const n = window.__canvas.getState().nodes.find(x=>x.id===id);
              if (!n) return null;
              return { x:Math.round(n.position.x), y:Math.round(n.position.y),
                       html:(n.data&&n.data.html||'').slice(0,40),
                       abs:(n.positionAbsolute&&{x:Math.round(n.positionAbsolute.x),y:Math.round(n.positionAbsolute.y)}) };
            }""", nid)

        # 真实鼠标拖拽
        node = pg.locator(".react-flow__node").first
        box = node.bounding_box()
        cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
        log("拖动前节点屏幕中心=(%.0f,%.0f) store=%s" % (cx, cy, read()))
        pg.mouse.move(cx, cy)
        pg.mouse.down()
        pg.mouse.move(cx + 260, cy + 180, steps=12)
        pg.mouse.up()
        pg.wait_for_timeout(500)
        after_drag = read()
        log("真实拖动后 store=%s" % after_drag)

        # 保存落地
        pg.evaluate("window.__ui.getState().setActive('workspace')")
        pg.wait_for_timeout(1500)

        enters = []
        for k in range(3):
            pg.click("[data-canvas-id='%s']" % C, timeout=8000)
            pg.wait_for_timeout(1200)
            enters.append(read())
            log("第%d次进入 store=%s" % (k+1, enters[-1]))
            pg.evaluate("window.__ui.getState().setActive('workspace')")
            pg.wait_for_timeout(500)

        base = json.dumps(after_drag, sort_keys=True)
        stable = all(json.dumps(e, sort_keys=True) == base for e in enters)
        log("=> 真实拖动后位置，多次进出是否完全一致: %s" % stable)
        if not stable:
            log("BUG: 真实拖动后节点位置/内容在多次进出中漂移")
            for i, e in enumerate(enters):
                log("   进入%d: %s" % (i+1, e))
        log("console errors: %d" % len(errs))
        for e in errs[:6]:
            log("  ERR:", e)

if __name__ == "__main__":
    main()
