"""诊断：节点位置多次进出的稳定性（验证拖动布局是否因进入即保存而漂移）。
模拟用户拖动节点（onNodesChange position），保存，往返多次进入，比对 position 是否稳定。
"""
import os, sys, time, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
def log(*a): print("[diag_pos]", *a, flush=True)

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
        pg.fill("input:visible >> nth=0", "tpos_%d@pea.ai" % int(time.time()))
        pg.fill("input:visible >> nth=1", "Passw0rd!")
        try: pg.click("button:has-text('注')", timeout=4000)
        except: pass
        pg.wait_for_timeout(800)
        try: pg.click("text=新建项目", timeout=4000)
        except: pass
        pg.wait_for_timeout(1000)

        C = pg.evaluate("window.__canvas.getState().canvasId")
        # 加一个节点
        pg.evaluate("window.__canvas.getState().addNode({ kind:'text', label:'T', meta:{} }, { x:100, y:100 })")
        pg.wait_for_timeout(400)
        nid = pg.evaluate("window.__canvas.getState().nodes[0].id")
        # 模拟拖动到 (520, 380)
        pg.evaluate("""(id) => {
          window.__canvas.getState().onNodesChange([{ id, type:'position', position:{x:520,y:380}, dragging:false }]);
        }""", nid)
        pg.wait_for_timeout(400)
        # 保存落地
        pg.evaluate("window.__ui.getState().setActive('workspace')")
        pg.wait_for_timeout(1500)

        pos = []
        for k in range(3):
            pg.click("[data-canvas-id='%s']" % C, timeout=8000)
            pg.wait_for_timeout(1200)
            p = pg.evaluate("""(id) => {
              const n = window.__canvas.getState().nodes.find(x=>x.id===id);
              return n ? {x:Math.round(n.position.x), y:Math.round(n.position.y)} : null;
            }""", nid)
            pos.append(p)
            log("第%d次进入 节点位置=%s" % (k+1, p))
            pg.evaluate("window.__ui.getState().setActive('workspace')")
            pg.wait_for_timeout(500)

        stable = len(set(json.dumps(x) for x in pos)) == 1
        log("=> 位置是否稳定一致: %s  (期望 520/380)" % stable)
        if not stable:
            log("BUG: 节点位置在多次进出后漂移")
        log("console errors: %d" % len(errs))

if __name__ == "__main__":
    main()
