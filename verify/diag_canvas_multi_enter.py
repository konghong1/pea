"""诊断：同一项目多次点击进入，展示数据不一致。
忠实复现用户操作：通过 UI 点击项目卡片进入画布，多次往返，比较每次进入后的数据。
用 data-canvas-id 精确点击「同一个项目」，隔离列表错位干扰。
同时记录每次返回后列表卡片 id 顺序，判断列表是否稳定。
"""
import os, sys, time, json
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

def log(*a):
    print("[diag_multi]", *a, flush=True)

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
        pg.fill("input:visible >> nth=0", "tmulti_%d@pea.ai" % int(time.time()))
        pg.fill("input:visible >> nth=1", "Passw0rd!")
        try:
            pg.click("button:has-text('注')", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(800)
        # 新建项目 -> 进画布
        try:
            pg.click("text=新建项目", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(1000)

        def cid():
            return pg.evaluate("window.__canvas ? window.__canvas.getState().canvasId : null")
        def read_store():
            return pg.evaluate("""() => {
              const s = window.__canvas.getState();
              const nodes = s.nodes.slice().sort((a,b)=>String(a.id).localeCompare(String(b.id))).map(n=>({
                id:n.id, kind:n.data&&n.data.kind, label:n.data&&n.data.label, html:(n.data&&n.data.html||'').slice(0,30),
                pos:{x:Math.round(n.position.x), y:Math.round(n.position.y)}
              }));
              return { canvasId: s.canvasId, version: s.version, n: nodes.length, nodes };
            }""")
        def list_ids():
            return pg.evaluate("[...document.querySelectorAll('.projects-card')].map(e=>e.getAttribute('data-canvas-id'))")
        def back():
            pg.evaluate("window.__ui.getState().setActive('workspace')")
            pg.wait_for_timeout(400)
        def enter(cid_val):
            pg.click("[data-canvas-id='%s']" % cid_val, timeout=8000)
            pg.wait_for_timeout(1300)

        C = cid()
        log("新建项目 canvasId=%s" % C)
        # 加 3 个差异化文本节点
        for i in range(1, 4):
            pg.evaluate("""(i) => {
              window.__canvas.getState().addNode({ kind:'text', label:'节点'+i, html:'内容-'+i, meta:{} }, { x:100+i*40, y:100+i*40 });
            }""", i)
            pg.wait_for_timeout(200)
        pg.wait_for_timeout(300)
        s0 = read_store()
        log("加节点后 n=%s version=%s" % (s0["n"], s0["version"]))
        # 触发保存落地
        pg.evaluate("window.__ui.getState().setActive('workspace')")
        pg.wait_for_timeout(1500)
        log("已保存并返回")

        # 多次点击进入同一项目
        snapshots = []
        orders = []
        for k in range(4):
            order = list_ids()
            orders.append(order)
            enter(C)
            s = read_store()
            snapshots.append(s)
            log("第%d次进入: canvasId=%s n=%s version=%s" % (k+1, s["canvasId"], s["n"], s["version"]))
            back()

        # 判定
        same_cid = all(s["canvasId"] == C for s in snapshots)
        std = [json.dumps(s["nodes"], sort_keys=True, ensure_ascii=False) for s in snapshots]
        same_content = len(set(std)) == 1
        stable_list = len(set([str(o) for o in orders])) == 1
        log("=> 每次进入的 canvasId 都等于 C(%s): %s" % (C, same_cid))
        log("=> 每次进入的节点内容完全一致: %s" % same_content)
        log("=> 列表卡片顺序是否稳定(每次返回后): %s" % stable_list)
        if not same_cid:
            log("BUG: 进入的项目 id 不稳定（点击可能被列表错位影响）")
        if same_cid and not same_content:
            log("BUG: 同一项目多次进入节点内容不同（openCanvas 读取/解析问题）")
        if same_cid and same_content:
            log("未复现进入数据不一致；差异可能源于列表顺序错位（用户点了不同项目）。列表顺序样本: %s" % orders)

        log("console errors: %d" % len(errs))
        for e in errs[:8]:
            log("  ERR:", e)

if __name__ == "__main__":
    main()
