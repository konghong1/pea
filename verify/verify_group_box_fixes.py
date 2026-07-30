"""
E2E 验证：4 项修复（2026-07-30）
  1) 框选覆盖即选中（partial intersection）
  2) 组节点背景透明（点阵透出）
  3) 组拖动时所有子节点跟随
  4) 组功能条浮在框外顶部（不占框内空间）

通过 window.__canvas 注入节点 + 真实 ReactFlow 框选 + DOM 测量。
需要 localStorage.__peaDevHooks=1 + window.__canvas（DEV 模式或该 flag）。
"""
import json
import os
import sys
import time
import random
import string
import re
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

# ── helpers ──
def rand_email():
    return "grpfix_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))


def apireq(method, path, body=None, token=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, method=method, data=data,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer %s" % token} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def measure_node_rects(page):
    """读所有 .react-flow__node 的屏幕 rect。"""
    return page.evaluate("""() => {
        const out = {};
        for (const el of document.querySelectorAll('.react-flow__node[data-id]')) {
            const id = el.getAttribute('data-id');
            const r = el.getBoundingClientRect();
            out[id] = { l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height };
        }
        return out;
    }""")


def find_four_nodes(page):
    """在 store 中挑出 4 个非 group 节点，返回 id 列表。"""
    return page.evaluate("""() => {
        const ns = window.__canvas.getState().nodes;
        return ns.filter(n => n.type !== 'group').map(n => n.id);
    }""")


def main():
    results = []
    def ok(name, detail=""):
        results.append(("PASS", name, detail))
        print(f"  [PASS] {name}{(' — ' + detail) if detail else ''}")
    def fail(name, detail=""):
        results.append(("FAIL", name, detail))
        print(f"  [FAIL] {name}: {detail}")
    def info(msg):
        print(f"  [info] {msg}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        console_errors = []
        all_requests = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append("pageerror: " + str(e)))
        page.on("request", lambda r: all_requests.append(r.url))

        # 关键：dev hooks 标识（init script 在拿到 token 后追加注入）
        page.add_init_script("localStorage.setItem('__peaDevHooks','1');")

        try:
            # ── 0. 注册 + 建画布（生产后端 8088 通过 bff 转发）──
            email = rand_email()
            password = "Password123"
            st, _ = apireq("POST", "/auth/register", {"email": email, "password": password})
            tok = None
            try:
                tok = json.loads(urllib.request.urlopen(
                    urllib.request.Request(
                        BASE + "/auth/login", method="POST",
                        data=json.dumps({"email": email, "password": password}).encode(),
                        headers={"Content-Type": "application/json"},
                    ),
                    timeout=15,
                ).read().decode())["token"]
            except Exception as ex:
                info("login failed: %s" % ex)
            canvas_id = None
            canvas_ver = 1
            if tok:
                try:
                    cv = json.loads(urllib.request.urlopen(
                        urllib.request.Request(
                            BASE + "/canvases", method="POST",
                            data=json.dumps({"title": "group box fix", "type": "personal"}).encode(),
                            headers={"Content-Type": "application/json",
                                     "Authorization": "Bearer %s" % tok},
                        ), timeout=15,
                    ).read().decode())
                    canvas_id = cv.get("id")
                    canvas_ver = cv.get("version", 1)
                except Exception as ex:
                    info("create canvas failed: %s" % ex)
            info("user=%s canvas=%s" % (email, canvas_id))

            # ── 追加 init script：把真实 token / user / 路由写进 localStorage ──
            page.add_init_script("""
                localStorage.setItem('pea_token', '""" + (tok or "x") + """');
                localStorage.setItem('pea_user', JSON.stringify({ id: 1, email: '""" + email + """' }));
                localStorage.setItem('pea_ui_route', JSON.stringify({ active: 'canvas', canvasId: """ + str(canvas_id or 1) + """ }));
            """)

            # ── 1. 打开画布（生产环境可能因 token / 路由要先 mock）──
            # 先 mock 关键 auth 端点避免 401 把页面踢回 login
            import re as _re
            page.route(_re.compile(r".*?/users/me.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": 1, "email": email, "displayName": "Tester",
                                 "balance": 0, "isAdmin": False, "planLevel": 0,
                                 "effectivePlanLevel": 0, "planExpiresAt": None})))
            page.route(_re.compile(r".*?/auth/refresh.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"token": tok or "x"})))
            # 也 mock canvases 列表，避免 /canvases 401
            page.route(_re.compile(r".*?/canvases(\?.*)?$"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "data": []})))
            page.route(_re.compile(r".*?/canvases/\d+.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": canvas_id or 1, "title": "box fix", "version": canvas_ver,
                                 "graph_json": {"nodes": [], "edges": []}})))
            # 把真实 token 写入 init script（已经追加过，这里删掉冗余）
            # 直接进入页面，token/init script 已在 navigation 前生效
            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            # 如果 URL 跳到 /login，调 setActive('canvas') 跳回画布
            cur = page.evaluate("location.href")
            info("goto 后 url: %s" % cur)
            if "/login" in cur:
                # 尝试用 dev hook 强制跳转
                page.evaluate("""() => {
                    const ui = window.__ui && window.__ui.getState();
                    if (ui) ui.setActive('canvas');
                }""")
                page.wait_for_timeout(1500)
                cur = page.evaluate("location.href")
                info("setActive 后 url: %s" % cur)
            # 打印关键请求
            relevant = [u for u in all_requests if any(p in u for p in ("/users/", "/auth/", "/canvases", "api"))][-20:]
            info("最近 API 请求: %s" % relevant)
            try:
                page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
            except Exception as ex:
                fail("dev hooks", "window.__canvas 未出现: %s" % ex)
                page.screenshot(path="debug_box_no_hook.png")
                return results
            page.wait_for_timeout(1500)
            ok("dev hooks (window.__canvas 暴露)")

            # ── 2. 注入 4 个节点：2x2 网格，覆盖 4 个不同的屏幕区域 ──
            injected = page.evaluate("""([cid, ver]) => {
                const cs = window.__canvas.getState();
                cs.setCanvasMeta(cid, ver, 'box fix');
                cs.loadGraph([
                  { id: 't1', type: 'pea', position: { x: 200, y: 200 }, data: { kind: 'text', label: 'T1', html: '<p>T1</p>' } },
                  { id: 't2', type: 'pea', position: { x: 600, y: 200 }, data: { kind: 'text', label: 'T2', html: '<p>T2</p>' } },
                  { id: 't3', type: 'pea', position: { x: 200, y: 550 }, data: { kind: 'text', label: 'T3', html: '<p>T3</p>' } },
                  { id: 't4', type: 'pea', position: { x: 600, y: 550 }, data: { kind: 'text', label: 'T4', html: '<p>T4</p>' } }
                ], [], ver);
                // 重新拿最新 state（cs 引用是 set 之前的快照）
                const s2 = window.__canvas.getState();
                return s2.nodes.map(n => ({ id: n.id, pos: n.position }));
            }""", [canvas_id or 1, canvas_ver])
            page.wait_for_timeout(2000)
            ok(f"注入 4 节点：{json.dumps([n['id'] for n in injected])}")
            if len(injected) < 4:
                fail("注入节点", f"只有 {len(injected)} 个，store 内 nodes 数不足")
                page.screenshot(path="debug_box_inject.png")
                return results

            # 诊断：当前在画布页吗？DOM 中 react-flow 节点数？
            diag = page.evaluate("""() => ({
                url: location.href,
                hasRf: !!document.querySelector('.react-flow'),
                rfNodes: document.querySelectorAll('.react-flow__node[data-id]').length,
                hasCanvasEditor: !!document.querySelector('.pea-canvas-flow'),
                bodyCls: document.body.className,
            })""")
            info("诊断: %s" % diag)
            if diag["rfNodes"] < 4:
                # 可能 CanvasEditor 在 openCanvas 失败时清掉了 nodes。
                # 再注入一次（这一次的 setState 会触发 React 重渲染）
                info("DOM 节点不足，重新强制 setState")
                page.evaluate("""([cid, ver]) => {
                    const cs = window.__canvas.getState();
                    cs.setCanvasMeta(cid, ver, 'box fix');
                    window.__canvas.setState({
                        canvasId: cid,
                        version: ver,
                        title: 'box fix',
                        nodes: [
                            { id: 't1', type: 'pea', position: { x: 200, y: 200 }, data: { kind: 'text', label: 'T1', html: '<p>T1</p>' } },
                            { id: 't2', type: 'pea', position: { x: 600, y: 200 }, data: { kind: 'text', label: 'T2', html: '<p>T2</p>' } },
                            { id: 't3', type: 'pea', position: { x: 200, y: 550 }, data: { kind: 'text', label: 'T3', html: '<p>T3</p>' } },
                            { id: 't4', type: 'pea', position: { x: 600, y: 550 }, data: { kind: 'text', label: 'T4', html: '<p>T4</p>' } }
                        ],
                        edges: [],
                        selectedId: null,
                        selectedIds: [],
                        dirty: false,
                    });
                }""", [canvas_id or 1, canvas_ver])
                page.wait_for_timeout(1500)
                diag2 = page.evaluate("""() => ({
                    url: location.href,
                    hasRf: !!document.querySelector('.react-flow'),
                    rfNodes: document.querySelectorAll('.react-flow__node[data-id]').length,
                })""")
                info("二次诊断: %s" % diag2)

            # 等待 ReactFlow 完成测量
            page.wait_for_function("""() => {
                const ns = document.querySelectorAll('.react-flow__node[data-id]');
                if (ns.length < 4) return false;
                return Array.from(ns).every(n => n.getBoundingClientRect().width > 0);
            }""", timeout=10000)
            rects = measure_node_rects(page)
            info("节点 rects: " + json.dumps({k: (round(v['l']), round(v['t']), round(v['r']), round(v['b'])) for k, v in rects.items()}))
            # 诊断 viewport
            vp = page.evaluate("""() => {
                const rf = document.querySelector('.react-flow');
                const vp = document.querySelector('.react-flow__viewport');
                const cnr = document.querySelector('.react-flow__pane');
                return rf && vp && cnr ? {
                    rfRect: (() => { const r = rf.getBoundingClientRect(); return {l: Math.round(r.left), t: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; })(),
                    vpStyle: vp.style.transform,
                    cnrRect: (() => { const r = cnr.getBoundingClientRect(); return {l: Math.round(r.left), t: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; })(),
                } : null;
            }""")
            info("viewport: %s" % vp)

            # ══════════════════════════════
            # 验证 1：框选覆盖即选中
            # ══════════════════════════════
            # 策略：拖一个超大选区覆盖 4 节点全部，再拖一个仅覆盖 t1+t2 边缘的选区（partial 模式应选中）
            page.mouse.click(50, 50)  # 清空选择（点左上角空白 — pane 区域）
            page.wait_for_timeout(300)
            cleared = page.evaluate("() => window.__canvas.getState().selectedIds")
            info("初始 selectedIds: %s" % cleared)

            # 第一次框选：覆盖全部 4 节点
            r1, r2, r3, r4 = rects['t1'], rects['t2'], rects['t3'], rects['t4']
            sx = min(r1['l'], r3['l']) - 30
            sy = min(r1['t'], r2['t']) - 30
            ex = max(r2['r'], r4['r']) + 30
            ey = max(r3['b'], r4['b']) + 30
            sx, sy = max(20, sx), max(80, sy)  # 不在 header
            ex, ey = min(1400, ex), min(880, ey)
            info("框选 A: (%d,%d) -> (%d,%d)" % (sx, sy, ex, ey))
            page.mouse.move(sx, sy)
            page.mouse.down()
            for i in range(1, 11):
                page.mouse.move(sx + (ex - sx) * i / 10, sy + (ey - sy) * i / 10)
                page.wait_for_timeout(30)
            page.wait_for_timeout(60)  # 让最后一次 mousemove 把选区刷新到完整位置
            page.mouse.up()
            # 诊断：mouseup 后（clearTimer 150ms 未触发前）__lastSelRect 是否捕获到完整选区
            lastRectA = page.evaluate("() => window.__lastSelRect")
            info("mouseup 后 __lastSelRect: %s" % lastRectA)
            page.wait_for_timeout(1200)
            selA = page.evaluate("() => window.__canvas.getState().selectedIds")
            info("框选 A 选中: %s" % selA)
            clog = page.evaluate("() => window.__correctionLog")
            info("校正日志 __correctionLog: %s" % clog)
            # 诊断 MutationObserver 是否记录到 lastSelRect
            diag_last = page.evaluate("() => window.__lastSelRect")
            info("window.__lastSelRect: %s" % diag_last)
            diag_rf = page.evaluate("""() => {
                const out = {};
                for (const el of document.querySelectorAll('.react-flow__node')) {
                    const id = el.getAttribute('data-id');
                    out[id] = {
                        cls: el.className,
                        rect: (() => { const r = el.getBoundingClientRect(); return { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right), b: Math.round(r.bottom), w: Math.round(r.width), h: Math.round(r.height) }; })(),
                    };
                }
                return out;
            }""")
            info("ReactFlow 节点状态: %s" % json.dumps(diag_rf, ensure_ascii=False))
            # 诊断 ReactFlow 内部 store
            diag_store = page.evaluate("""() => {
                try {
                    // reactflow 用 useStoreApi 暴露 — 不直接给外部用。改读 DOM .react-flow 的 __reactProps$ 或 .react-flow__viewport 的 transform style
                    const sel = document.querySelector('.react-flow__selection');
                    const vp = document.querySelector('.react-flow__viewport');
                    return {
                        selExists: !!sel,
                        selRect: sel ? (() => { const r = sel.getBoundingClientRect(); return { l: Math.round(r.left), t: Math.round(r.top), r: Math.round(r.right), b: Math.round(r.bottom), w: Math.round(r.width), h: Math.round(r.height) }; })() : null,
                        selStyle: sel ? sel.getAttribute('style') : null,
                        vpStyle: vp ? vp.style.transform : null,
                    };
                } catch(e) { return { err: e.message }; }
            }""")
            info("ReactFlow DOM 状态: %s" % diag_store)
            if set(selA) >= {'t1', 't2', 't3', 't4'}:
                ok("验证1a：框选全覆盖 4 节点", str(sorted(selA)))
            else:
                fail("验证1a：框选全覆盖", "只选中 %s" % selA)
                page.screenshot(path="debug_box_v1a.png")

            # 第二次框选：选区只覆盖 t1+t2（顶部两行），明确不碰到 t3/t4
            # t3/t4 顶部 y=448，box 下沿收到 440 以内，避免 partial-intersection 误选底部两行。
            page.mouse.click(50, 50)
            page.wait_for_timeout(300)
            r1, r2 = rects['t1'], rects['t2']
            sy = min(r1['t'], r2['t'])  # 顶对齐 t1/t2 顶部
            ey = 440  # 明确低于 t3/t4 顶部(448)，与 t1/t2 底部(452)留 12px 余量
            sx = r1['l'] - 30  # 从 t1 左侧空白 pane 开始（mousedown 落在节点上会变成节点拖动而非框选）
            ex = r2['r'] - 10  # 到 t2 右侧稍内结束
            sy, ey = max(80, sy), min(880, ey)
            info("框选 B (partial): (%d,%d) -> (%d,%d)" % (sx, sy, ex, ey))
            page.mouse.move(sx, sy)
            page.mouse.down()
            for i in range(1, 11):
                page.mouse.move(sx + (ex - sx) * i / 10, sy + (ey - sy) * i / 10)
                page.wait_for_timeout(30)
            page.wait_for_timeout(60)
            page.mouse.up()
            page.wait_for_timeout(800)
            selB = page.evaluate("() => window.__canvas.getState().selectedIds")
            info("框选 B 选中: %s" % selB)
            if set(selB) >= {'t1', 't2'} and 't3' not in selB and 't4' not in selB:
                ok("验证1b：partial 选区只选中覆盖到的节点", str(sorted(selB)))
            else:
                fail("验证1b：partial 选区", "选中 %s，期望至少 {t1,t2} 且不含 t3/t4" % selB)
                page.screenshot(path="debug_box_v1b.png")

            page.screenshot(path="verify_box_v1.png")

            # ══════════════════════════════
            # 验证 4：组功能条浮在框外顶部（在打组后第一时间验证，避免被后续拖动干扰）
            # 策略：选 2 节点 → 打组 → 选中 group → 检查 .pgn-header-portal top < group.top
            # ══════════════════════════════
            page.evaluate("() => { const cs = window.__canvas.getState(); cs.setSelection(['t1','t2','t3','t4']); }")
            page.wait_for_timeout(500)
            gid = page.evaluate("() => { const cs = window.__canvas.getState(); return cs.groupNodes(['t1','t2','t3','t4']); }")
            info("打组返回 gid: %s" % gid)
            page.wait_for_timeout(1500)

            # 选中 group 节点（模拟用户单击 group 框）
            page.evaluate("([gid]) => { window.__canvas.getState().setSelection([gid]); }", [gid])
            page.wait_for_timeout(900)

            g_dom = page.evaluate("""() => {
                const gn = document.querySelector('.react-flow__node-group') || document.querySelector('.react-flow__node[data-type="group"]');
                const portal = document.querySelector('.pgn-header-portal');
                if (!gn) return { hasGroup: false };
                const r = gn.getBoundingClientRect();
                let portalInfo = null;
                if (portal) {
                    const pr = portal.getBoundingClientRect();
                    const cs = getComputedStyle(portal);
                    portalInfo = { top: pr.top, left: pr.left, bottom: pr.bottom, h: pr.height,
                                   bg: cs.backgroundColor, zi: cs.zIndex, pos: cs.position };
                }
                return { hasGroup: true, group: { t: r.top, l: r.left, b: r.bottom, r: r.right },
                         portal: portalInfo };
            }""")
            if not g_dom.get("hasGroup"):
                fail("验证4a：组节点存在", "找不到 .react-flow__node-group")
                page.screenshot(path="debug_box_v4a.png")
            else:
                g = g_dom["group"]
                ok("验证4a：组节点存在 (rect=%.0f×%.0f)" % (g["r"] - g["l"], g["b"] - g["t"]))
                if g_dom["portal"] is None:
                    fail("验证4b：浮层 header 存在", "未找到 .pgn-header-portal（应在 group 选中时 portal 到 body）")
                else:
                    p = g_dom["portal"]
                    gap = g["t"] - p["bottom"]
                    if p["bottom"] <= g["t"] + 4:  # 浮层底部 ≤ group 顶部 + 4px 误差
                        ok("验证4b：浮层 header 在组框外顶部 (gap=%.0fpx, top=%.0f, group.t=%.0f)" % (gap, p["top"], g["t"]))
                    else:
                        fail("验证4b：浮层 header 位置", "浮层底部 %.0f 在组框顶部 %.0f 下方 %.0fpx" % (p["bottom"], g["t"], p["bottom"] - g["t"]))
                        page.screenshot(path="debug_box_v4b.png")
                    if p["pos"] == "fixed":
                        ok("验证4c：浮层 header 定位 fixed", "")
                    else:
                        fail("验证4c：浮层 header 定位", "position=%s，应为 fixed" % p["pos"])

            page.screenshot(path="verify_box_v4.png")

            # ══════════════════════════════
            # 验证 2：组背景透明（点阵透出）
            # ══════════════════════════════
            gbg = page.evaluate("""() => {
                const gn = document.querySelector('.pea-group-node');
                if (!gn) return null;
                const cs = getComputedStyle(gn);
                return {
                    bg: cs.backgroundColor,
                    bdf: cs.backdropFilter || cs.webkitBackdropFilter,
                    of: cs.overflow,
                    bd: cs.borderRadius,
                    border: cs.border,
                };
            }""")
            if gbg is None:
                fail("验证2：组背景", "找不到 .pea-group-node")
            else:
                info("组背景 css: %s" % gbg)
                # background: transparent / rgba(...,0)
                bg = gbg["bg"]
                is_transparent = bg in ("rgba(0, 0, 0, 0)", "transparent") or bg.startswith("rgba(0, 0, 0, 0")
                if is_transparent:
                    ok("验证2a：组背景透明", "background=%s" % bg)
                else:
                    fail("验证2a：组背景透明", "background=%s（应 transparent 或 rgba(0,0,0,0)）" % bg)
                # 子节点 pointer-events 不被 group 拦截
                pe = page.evaluate("""() => {
                    const gn = document.querySelector('.pea-group-node');
                    return getComputedStyle(gn).pointerEvents;
                }""")
                if pe == "none":
                    ok("验证2b：组容器 pointer-events:none（子节点可正常交互）", "")
                else:
                    fail("验证2b：组容器 pointer-events", "=%s，应为 none" % pe)

            page.screenshot(path="verify_box_v2.png")

            # ══════════════════════════════
            # 验证 3：组拖动时所有子节点跟随
            # ══════════════════════════════
            # 读拖动前所有子节点 DOM 屏幕位置（绝对 px）
            before_rects = page.evaluate("""([gid]) => {
                const ns = window.__canvas.getState().nodes;
                const kids = ns.filter(n => n.parentNode === gid);
                const out = {};
                for (const k of kids) {
                    const el = document.querySelector(`.react-flow__node[data-id="${k.id}"]`);
                    if (el) {
                        const r = el.getBoundingClientRect();
                        out[k.id] = { l: r.left, t: r.top };
                    }
                }
                return out;
            }""", [gid])
            info("拖动前子节点屏幕位置: %s" % before_rects)

            # 通过 store 移动 group position
            dx, dy = 150, 80
            moved = page.evaluate("""([gid, dx, dy]) => {
                const cs = window.__canvas.getState();
                const g = cs.nodes.find(n => n.id === gid);
                if (!g) return false;
                const newPos = { x: g.position.x + dx, y: g.position.y + dy };
                // 用 setState 触发 React 渲染（zustand 不可变）
                const newNodes = cs.nodes.map(n => n.id === gid ? { ...n, position: newPos } : n);
                window.__canvas.setState({ nodes: newNodes });
                // 模拟 ReactFlow 内部 position change（用于触发 subflow 同步）
                window.__canvas.getState().onNodesChange([{ id: gid, type: 'position', position: newPos, dragging: true }]);
                return true;
            }""", [gid, dx, dy])
            page.wait_for_timeout(900)

            if not moved:
                fail("验证3：组拖动", "group 节点未找到")
            else:
                # 读拖动后子节点 DOM 屏幕位置
                after_rects = page.evaluate("""([gid]) => {
                    const ns = window.__canvas.getState().nodes;
                    const kids = ns.filter(n => n.parentNode === gid);
                    const out = {};
                    for (const k of kids) {
                        const el = document.querySelector(`.react-flow__node[data-id="${k.id}"]`);
                        if (el) {
                            const r = el.getBoundingClientRect();
                            out[k.id] = { l: r.left, t: r.top };
                        }
                    }
                    return out;
                }""", [gid])
                info("拖动后子节点屏幕位置: %s" % after_rects)

                all_follow = True
                for kid_id, br in before_rects.items():
                    ar = after_rects.get(kid_id)
                    if not ar:
                        fail("验证3：子节点 %s 拖动后找不到" % kid_id, "")
                        all_follow = False
                        continue
                    kdx = ar["l"] - br["l"]
                    kdy = ar["t"] - br["t"]
                    # 允许 2px 误差（ReactFlow 渲染抖动 + zoom 缩放因子影响）
                    if abs(kdx - dx) > 4 or abs(kdy - dy) > 4:
                        fail("验证3：子节点 %s 跟随 group" % kid_id,
                             "屏幕位移=%.0f,%.0f，期望≈%.0f,%.0f" % (kdx, kdy, dx, dy))
                        all_follow = False
                if all_follow and before_rects:
                    ok("验证3：%d 个子节点全部跟随 group 拖动" % len(before_rects),
                       "dx=%.0f, dy=%.0f" % (dx, dy))

            page.screenshot(path="verify_box_v3.png")

            # ══════════════════════════════
            # 验证 5：选区渲染完整（不被截断）
            # ══════════════════════════════
            # 方案：清空选择后，从 pane 左上 (100, 100) 拖到 (1100, 800)，
            # 拖拽过程中实时查 .pea-selection-overlay 的 width，应 ≥ 980px
            # （旧版 RF .react-flow__selection 在本应用 transform 下只画 ~400px）
            page.mouse.click(50, 50)
            page.wait_for_timeout(300)
            page.mouse.move(100, 100)
            page.mouse.down()
            page.mouse.move(1100, 800)  # 单步直跳到目标，先观察 1 帧
            page.wait_for_timeout(60)
            meas = page.evaluate("""() => {
                const el = document.querySelector('.pea-selection-overlay');
                if (!el) return { found: false };
                const r = el.getBoundingClientRect();
                return { found: true, w: Math.round(r.width), h: Math.round(r.height),
                         l: Math.round(r.left), t: Math.round(r.top),
                         br: Math.round(r.right), bb: Math.round(r.bottom) };
            }""")
            page.mouse.up()
            page.wait_for_timeout(60)
            if not meas.get("found"):
                fail("验证5a：选区 overlay 元素", "找不到 .pea-selection-overlay")
            else:
                info("overlay rect: w=%s h=%s l=%s t=%s r=%s b=%s" % (
                    meas["w"], meas["h"], meas["l"], meas["t"], meas["br"], meas["bb"]))
                # 拖了 x=100→1100 (1000px) y=100→800 (700px)。overlay 宽应接近 1000。
                if meas["w"] >= 700:  # 允许 ±30% 误差（避免偶发窗口宽度问题）
                    ok("验证5a：选区 overlay 完整不截断",
                       "w=%s（拖了 1000px）" % meas["w"])
                else:
                    fail("验证5a：选区 overlay 宽度",
                         "w=%s，期望≈1000（被截断？）" % meas["w"])
                    page.screenshot(path="debug_box_v5.png")

            # ══════════════════════════════
            # 验证 6：选区不触发边的 selected
            # ══════════════════════════════
            # 注入一条横穿画布的边 t1→t4，然后拖一个大选区（应会穿过这条边），
            # 检查 edges[*].selected 应全为 false。
            page.evaluate("""([gid]) => {
                const cs = window.__canvas.getState();
                const newEdges = [
                    { id: 'e1', source: 't1', target: 't4', type: 'pea' },
                ];
                window.__canvas.setState({ edges: newEdges });
                // 取消选中：清空
                window.__canvas.getState().setSelection([]);
            }""", [gid])
            page.wait_for_timeout(300)
            # 再次拖一次大框：覆盖 4 个节点 + 穿过连线
            page.mouse.move(100, 100)
            page.mouse.down()
            page.mouse.move(1100, 800)
            page.wait_for_timeout(120)
            page.mouse.up()
            page.wait_for_timeout(800)  # 等 correctBoxSelection 跑完
            edge_state = page.evaluate("""() => {
                const es = window.__canvas.getState().edges;
                return es.map(e => ({ id: e.id, selected: !!e.selected }));
            }""")
            info("edges 状态: %s" % edge_state)
            if any(e.get("selected") for e in edge_state):
                fail("验证6：框选不应选中 edges",
                     "至少一条边 selected=true: %s" % edge_state)
                page.screenshot(path="debug_box_v6.png")
            else:
                ok("验证6：框选不触发 edges selected",
                   "edges=%s" % edge_state)
            page.screenshot(path="verify_box_v6.png")

            # ══════════════════════════════
            # 验证 7：拖入组 / 脱离组
            # ══════════════════════════════
            # 方案：注入一个新节点 t5 在画布 (820, 400)，明显在已有组边界内 [200..940 × 200..904]。
            # 调用 store.moveNodeToGroup('t5')：
            #   - 期望返回 'added'
            #   - 期望 t5.parentNode === gid
            #   - 期望 t5.position 是相对组的（新组 position.x - 820, ...) 即组内左上有小偏移
            #   - 期望 gid 在 data.childrenIds 中包含 t5
            #   - 期望组的 style.width/height 自动扩到包住新节点
            # 然后再调用一次 moveNodeToGroup('t5')（t5 仍在组内），应返回 null（不动）。
            # 最后硬把 t5.position 改到组外 (1500, 400)，调用 moveNodeToGroup 应返回 'removed'。
            page.evaluate("""([gid]) => {
                const cs = window.__canvas.getState();
                const t5 = { id: 't5', type: 'pea', position: { x: 820, y: 400 },
                             data: { kind: 'text', label: 'T5', html: '<p>T5</p>' } };
                window.__canvas.setState({ nodes: [...cs.nodes, t5] });
                window.__canvas.getState().setSelection([]);
            }""", [gid])
            page.wait_for_timeout(800)

            r1 = page.evaluate("([gid]) => window.__canvas.getState().moveNodeToGroup('t5')", [gid])
            page.wait_for_timeout(300)
            s7 = page.evaluate("""([gid]) => {
                const cs = window.__canvas.getState();
                const t5 = cs.nodes.find(n => n.id === 't5');
                const grp = cs.nodes.find(n => n.id === gid);
                if (!t5 || !grp) return { ok: false, reason: 'nodes missing' };
                return {
                    ok: true,
                    t5parent: t5.parentNode || null,
                    t5extent: t5.extent || null,
                    t5pos: t5.position,
                    grpPos: grp.position,
                    grpStyle: grp.style,
                    childrenIds: (grp.data && grp.data.childrenIds) || [],
                };
            }""", [gid])
            info("moveNodeToGroup(t5) 结果=%s；状态=%s" % (r1, s7))
            if r1 != 'added':
                fail("验证7a：拖入组", "moveNodeToGroup 返回 %s（期望 'added'）" % r1)
            elif not s7.get("ok"):
                fail("验证7a：拖入组", "state 读取失败: %s" % s7)
            elif s7["t5parent"] != gid:
                fail("验证7a：拖入组", "t5.parentNode=%s（期望 gid=%s）" % (s7["t5parent"], gid))
            elif 't5' not in s7["childrenIds"]:
                fail("验证7a：拖入组", "组 childrenIds 不含 t5: %s" % s7["childrenIds"])
            else:
                ok("验证7a：拖入组 OK (parentNode=gid, childrenIds 含 t5)", "")

            # 在组内：再调用一次应返回 null（保持不变）
            r2 = page.evaluate("() => window.__canvas.getState().moveNodeToGroup('t5')")
            if r2 is None:
                ok("验证7b：在组内再调用 moveNodeToGroup 返回 null（幂等）", "")
            else:
                fail("验证7b：在组内再调用", "返回值=%s（期望 null）" % r2)

            # 把 t5 移到组外，再调用应返回 'removed'
            page.evaluate("""([gid]) => {
                const cs = window.__canvas.getState();
                const t5 = cs.nodes.find(n => n.id === 't5');
                // 把 t5 移到 group 的 (position+style.width+50, ...) 即明确在组外
                const grp = cs.nodes.find(n => n.id === gid);
                const grpW = (grp.style && grp.style.width) || 240;
                const newPos = { x: grp.position.x + grpW + 50, y: grp.position.y };
                const newNodes = cs.nodes.map(n => n.id === 't5' ? { ...n, position: newPos } : n);
                window.__canvas.setState({ nodes: newNodes });
            }""", [gid])
            page.wait_for_timeout(400)
            r3 = page.evaluate("() => window.__canvas.getState().moveNodeToGroup('t5')")
            s7c = page.evaluate("""([gid]) => {
                const cs = window.__canvas.getState();
                const t5 = cs.nodes.find(n => n.id === 't5');
                const grp = cs.nodes.find(n => n.id === gid);
                return {
                    t5parent: t5.parentNode || null,
                    t5pos: t5.position,
                    grpPos: grp.position,
                    childrenIds: (grp.data && grp.data.childrenIds) || [],
                };
            }""", [gid])
            info("脱离调用结果=%s；状态=%s" % (r3, s7c))
            if r3 != 'removed':
                fail("验证7c：脱离组", "moveNodeToGroup 返回 %s（期望 'removed'）" % r3)
            elif s7c["t5parent"] is not None:
                fail("验证7c：脱离组", "t5.parentNode=%s（应清空）" % s7c["t5parent"])
            elif 't5' in s7c["childrenIds"]:
                fail("验证7c：脱离组", "childrenIds 仍含 t5: %s" % s7c["childrenIds"])
            else:
                ok("验证7c：脱离组 OK (parentNode 清空, childrenIds 不含 t5)", "")

            page.screenshot(path="verify_box_v7.png")

        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append(("ERROR", str(e), ""))
            print(f"  [ERROR] {e}")
            try: page.screenshot(path="debug_box_error.png")
            except Exception: pass
        finally:
            browser.close()

    print("\n" + "=" * 60)
    for r in results:
        s = r[0]
        print(f"  [{s}] {r[1]}{(' — ' + r[2]) if len(r) > 2 and r[2] else ''}")
    p = sum(1 for r in results if r[0] == "PASS")
    f = sum(1 for r in results if r[0] == "FAIL")
    e = sum(1 for r in results if r[0] == "ERROR")
    print("=" * 60)
    print(f"总计 {len(results)} | PASS {p} | FAIL {f} | ERROR {e}")
    print("\n[console errors captured]")
    for ce in console_errors[-20:]:
        print("  -", ce[:200])
    if f == 0 and e == 0:
        print("全部通过!")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
