"""复现并诊断：框选打组后 节点拖不出 / 选择框变大 / 边框残缺。
目标：localhost:5180 (vite dev, 支持 HMR)。
输出每个阶段的诊断数据，供修复前后对比。
"""
import json
import time
import re
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "grp_%s@pea.ai" % STAMP
PW = "Password123"


def ls_set(page, key, value):
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))


def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer %s" % token} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return 500, {}


def rect_of(page, sel):
    return page.evaluate("""(s) => {
        const el = document.querySelector(s);
        if (!el) return null;
        const b = el.getBoundingClientRect();
        return { left:+b.left.toFixed(1), top:+b.top.toFixed(1), right:+b.right.toFixed(1),
                 bottom:+b.bottom.toFixed(1), w:+b.width.toFixed(1), h:+b.height.toFixed(1) };
    }""", sel)


def node_state(page, nid):
    return page.evaluate("""(id) => {
        const n = window.__canvas.getState().nodes.find(x => x.id === id);
        if (!n) return null;
        return { id, parentNode: n.parentNode || null, extent: n.extent || null,
                 pos: n.position, selected: !!n.selected,
                 w: n.width || null, h: n.height || null };
    }""", nid)


def group_state(page, gid):
    return page.evaluate("""(id) => {
        const n = window.__canvas.getState().nodes.find(x => x.id === id);
        if (!n) return null;
        return { id, type: n.type, pos: n.position,
                 style: n.style, childrenIds: (n.data||{}).childrenIds || [] };
    }""", gid)


def setup_graph(page):
    page.evaluate("""() => {
        const cs = window.__canvas.getState();
        cs.loadGraph([
            {id:'n1', type:'pea', position:{x:300,y:200}, data:{kind:'text', label:'T1', html:'A'}},
            {id:'n2', type:'pea', position:{x:300,y:420}, data:{kind:'text', label:'T2', html:'B'}},
            {id:'n3', type:'pea', position:{x:800,y:200}, data:{kind:'text', label:'T3', html:'C'}},
            {id:'n4', type:'pea', position:{x:800,y:420}, data:{kind:'text', label:'T4', html:'D'}}
        ], [], 1);
    }""")


def drag(page, from_sel, to_x, to_y, steps=20):
    r = rect_of(page, from_sel)
    if not r:
        raise Exception("drag source not found: " + from_sel)
    sx, sy = (r["left"] + r["w"] / 2), (r["top"] + r["h"] / 2)
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.wait_for_timeout(60)
    page.mouse.move(to_x, to_y, steps=steps)
    page.wait_for_timeout(60)
    page.mouse.up()
    page.wait_for_timeout(400)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = ctx.new_page()
    page.on("pageerror", lambda e: print("PAGEERROR:", e))

    api("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    st, resp = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})
    tok = (resp or {}).get("token")
    cvs = api("POST", "/canvases", token=tok, body={"title": "grp", "type": "personal"})[1]

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    ls_set(page, "pea_token", tok or "x")
    ls_set(page, "pea_user", {"id": 1, "email": EMAIL})
    ls_set(page, "pea_ui_route", {"active": "canvas", "canvasId": None})

    def mock_json(payload):
        return lambda route, request: route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/users/me", mock_json({"id": 1, "email": EMAIL, "displayName": "T", "balance": 0,
                                         "isAdmin": False, "planLevel": 0, "effectivePlanLevel": 0, "planExpiresAt": None}))
    page.route("**/auth/refresh", mock_json({"token": tok or "x"}))
    page.route(re.compile(r"http://[^/]+/canvases.*"), mock_json({"ok": True, "data": []}))
    page.route("**/models/**", mock_json([]))
    page.route("**/files/**", mock_json({"ok": True}))

    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => window.__canvas && window.__ui", timeout=20000)
    page.evaluate("() => { window.__ui.getState().setActive('canvas'); window.__canvas.getState().setCanvasMeta(%s, %s, 'grp'); }"
                  % (json.dumps(cvs["id"]), json.dumps(cvs["version"])))
    page.wait_for_timeout(800)
    mount = page.evaluate("""() => {
        return {
            active: window.__ui.getState().active,
            hasFlow: !!document.querySelector('.react-flow'),
            nodeCount: document.querySelectorAll('.react-flow__node').length
        };
    }""")
    print("[挂载诊断]", mount)

    print("=== 阶段0: 载入 4 个自由节点 ===")
    setup_graph(page)
    page.wait_for_timeout(800)
    for n in ["n1", "n2", "n3", "n4"]:
        print("  ", node_state(page, n))

    print("\n=== 阶段1: 框选 n1,n2 打组 ===")
    page.evaluate("() => window.__canvas.getState().groupNodes(['n1','n2'])")
    page.wait_for_timeout(800)
    g = page.evaluate("() => { const ns = window.__canvas.getState().nodes; return ns.filter(n=>n.type==='group').map(n=>({id:n.id, children:(n.data||{}).childrenIds, parentOfN1: ns.find(x=>x.id==='n1').parentNode})); }")
    print("  groups:", g)
    gid = g[0]["id"] if g else None
    print("  group state:", group_state(page, gid))
    print("  n1 state:", node_state(page, "n1"))
    dump = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('.react-flow__node')).map(el => ({
            id: el.getAttribute('data-id'),
            cls: el.className,
            w: el.getBoundingClientRect().width,
            h: el.getBoundingClientRect().height,
            vis: getComputedStyle(el).visibility
        }));
    }""")
    print("  [DOM] 所有 .react-flow__node:", dump)
    print("  .pea-selection-bounds:", rect_of(page, ".pea-selection-bounds"))
    print("  .pea-group-node rect:", rect_of(page, ".react-flow__node[data-id='%s']" % gid))
    page.screenshot(path="verify/shots/stage1_group_selected.png")

    print("\n=== 阶段2 (#1 只能进不能出): 尝试把 n1 拖出组外 ===")
    gr = rect_of(page, ".react-flow__node[data-id='%s']" % gid)
    # 目标点：组边界外右侧空白
    target_x = int(gr["right"] + 250)
    target_y = int(gr["top"] + 40)
    page.evaluate("window.__lastGroupMove = null")
    drag(page, ".react-flow__node[data-id='n1']", target_x, target_y)
    last = page.evaluate("() => window.__lastGroupMove || null")
    print("  onNodeDragStop->moveNodeToGroup 结果:", last)
    print("  拖拽后 n1 state:", node_state(page, "n1"))
    print("  拖拽后 group childrenIds:", group_state(page, gid)["childrenIds"])

    print("\n=== 阶段3 (#2/#3 拖入后选择框变大/边框残缺): 把自由节点 n3 拖入组 ===")
    drag(page, ".react-flow__node[data-id='n3']", int(gr["left"] + gr["w"]/2), int(gr["top"] + gr["h"]/2))
    last = page.evaluate("() => window.__lastGroupMove || null")
    print("  onNodeDragStop->moveNodeToGroup 结果:", last)
    print("  拖入后 group state:", group_state(page, gid))
    print("  拖入后 n3 state:", node_state(page, "n3"))
    print("  .pea-selection-bounds:", rect_of(page, ".pea-selection-bounds"))
    print("  .pea-group-node rect:", rect_of(page, ".react-flow__node[data-id='%s']" % gid))
    print("  group 真实内容包围盒(dom):", rect_of(page, ".react-flow__node[data-id='%s'] .pea-group-node" % gid))

    # 测量 selection-bounds 与 group 框的差异
    sb = rect_of(page, ".pea-selection-bounds")
    gr2 = rect_of(page, ".react-flow__node[data-id='%s']" % gid)
    if sb and gr2:
        print("  [对比] selection-bounds 尺寸 %.0fx%.0f vs group 框 %.0fx%.0f (差值 w=%.0f h=%.0f)"
              % (sb["w"], sb["h"], gr2["w"], gr2["h"], sb["w"]-gr2["w"], sb["h"]-gr2["h"]))
    page.screenshot(path="verify/shots/stage3_after_drag_in.png")

    # 模拟拖拽过程中观察 selection-bounds 是否边框残缺：连续采样
    print("\n=== 阶段4: 拖动 n2(组内角落) 观察 selection-bounds 边框 ===")
    # 选中整个组
    page.evaluate("() => window.__canvas.getState().select(%s)" % json.dumps(gid))
    page.wait_for_timeout(300)
    # 拖 n2 一点点
    n2r = rect_of(page, ".react-flow__node[data-id='n2']")
    sx = n2r["left"] + n2r["w"]/2
    sy = n2r["top"] + n2r["h"]/2
    page.mouse.move(sx, sy); page.mouse.down(); page.wait_for_timeout(50)
    for i in range(1, 6):
        page.mouse.move(sx + i*15, sy + i*10, steps=2)
        page.wait_for_timeout(40)
        sb2 = rect_of(page, ".pea-selection-bounds")
        print("    step%d selection-bounds: %s" % (i, sb2))
        if i == 3:
            page.screenshot(path="verify/shots/stage4_dragging_group_selected.png")
    page.mouse.up()
    page.wait_for_timeout(300)

    browser.close()
    print("\nDONE")
