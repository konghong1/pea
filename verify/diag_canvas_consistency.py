"""诊断：同一画布两次进入数据不一致。
假设根因：改动画布后赶在 1s 自动保存前返回工作空间，CanvasEditor 卸载时
save effect 的 cleanup 取消了 pending 的 setTimeout 保存 -> 改动丢失 ->
第二次进入 GET 到的是后端旧数据，表现为「两次进入不一致」。

用 window.__ui.setActive('workspace') 精确触发 CanvasEditor 卸载（等同于点返回）。
"""
import os, sys, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

def log(*a):
    print("[diag_canvas]", *a, flush=True)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        pg = ctx.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append("PAGEERR:" + str(e)))
        pg.goto(BASE, wait_until="networkidle")
        pg.wait_for_timeout(400)

        # 注册/登录
        try:
            pg.click("text=去注册", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(300)
        pg.fill("input:visible >> nth=0", "tcheck_%d@pea.ai" % int(time.time()))
        pg.fill("input:visible >> nth=1", "Passw0rd!")
        try:
            pg.click("button:has-text('注')", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(800)
        # 新建项目 -> 直接进画布
        try:
            pg.click("text=新建项目", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(1000)

        def cid():
            return pg.evaluate("window.__canvas ? window.__canvas.getState().canvasId : null")
        def snap():
            return pg.evaluate("() => { const s = window.__canvas.getState(); return { n: s.nodes.length, ids: s.nodes.map(x=>x.id), saveCount: s.saveCount, dirty: s.dirty, version: s.version }; }")

        canvasId = cid()
        log("进入画布 canvasId=%s" % canvasId)
        s0 = snap()
        log("初始状态 nodes=%s saveCount=%s dirty=%s" % (s0["n"], s0["saveCount"], s0["dirty"]))

        # 加一个文本节点（直接走 store action，触发 dirty + 自动保存 effect）
        pg.evaluate("""() => {
          const c = window.__canvas.getState();
          c.addNode({ kind:'text', label:'一致性测试节点', meta:{} }, { x:140, y:140 });
        }""")
        pg.wait_for_timeout(300)
        s1 = snap()
        log("加节点后 nodes=%s dirty=%s saveCount=%s（dirty 应为 true）" % (s1["n"], s1["dirty"], s1["saveCount"]))

        # 关键：赶在 1s 自动保存前「返回工作空间」-> CanvasEditor 卸载 -> cleanup 取消 pending save
        pg.evaluate("window.__ui.getState().setActive('workspace')")
        pg.wait_for_timeout(200)
        log("已触发返回工作空间（CanvasEditor 应已卸载）")
        # 等足够久，看是否还有保存请求发出
        pg.wait_for_timeout(2000)
        s2 = snap()
        log("返回后 saveCount=%s（若未增加 => 改动未被保存，bug 已复现）" % s2["saveCount"])

        # 再次进入同一画布（模拟用户点同一个画布）
        pg.evaluate("window.__canvas.getState().openCanvas(%s)" % canvasId)
        pg.wait_for_timeout(1400)
        s3 = snap()
        log("再次进入画布 nodes=%s saveCount=%s dirty=%s" % (s3["n"], s3["saveCount"], s3["dirty"]))

        # 判定
        if s3["n"] >= 1:
            log("RESULT: 改动已持久化（未复现丢失）。可能根因在别处。")
        else:
            log("RESULT: BUG 复现 — 改动丢失！首次进入有 %d 个节点，再次进入只有 %d 个。" % (s1["n"], s3["n"]))

        # 额外：测「纯读取一致性」（无改动，两次 openCanvas 同一 id）
        pg.evaluate("window.__ui.getState().setActive('workspace')")
        pg.wait_for_timeout(300)
        pg.evaluate("window.__canvas.getState().openCanvas(%s)" % canvasId)
        pg.wait_for_timeout(1200)
        sa = pg.evaluate("JSON.stringify(window.__canvas.getState().nodes)")
        pg.evaluate("window.__canvas.getState().openCanvas(%s)" % canvasId)
        pg.wait_for_timeout(1200)
        sb = pg.evaluate("JSON.stringify(window.__canvas.getState().nodes)")
        log("纯读取一致性: 两次 openCanvas 同一 id 的 nodes 是否相等 = %s" % (sa == sb))

        log("console errors: %d" % len(errs))
        for e in errs[:10]:
            log("  ERR:", e)

if __name__ == "__main__":
    main()
