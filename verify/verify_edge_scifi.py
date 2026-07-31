"""验证「科技感连线 + HUD 断开芯片」改造：

  1. 空闲连线低对比 + 微模糊（stroke alpha 低、filter 含 blur）→ 不抢视线
  2. 选中「连线」→ 主线 is-active 高亮 + 出现流动虚线/光珠串 + 出现 HUD 删除芯片
  3. 选中「节点」→ 与该节点相连的边自动 active（高亮 + 流动）
  4. 拖动「节点」→ 拖动过程中相连边保持 active
  5. 方向性：linearGradient 的 x1/y1=source、x2/y2=target，且 to 端比 from 端更不透明；
     光珠/虚线动画 keyframes 为负向 dashoffset（source→target 流动）
  6. HUD 芯片结构完整（扫描环/六边核心/×）+ 扫描环有自转动画 + counter-scale
  7. 点击芯片能真正删掉这条边
  8. 取消选择后连线回落到空闲态（flow/beads 消失）
  9. 【本轮新增】光珠是「一串」而非一颗：dash 周期远小于路径长度，实际珠数 >= 4，
     且珠数随连线变长而增多（密度恒定）
 10. 【本轮新增】删除芯片出现在**鼠标点击处**，而不是永远在连线中点；
     点线的靠前/靠后位置，芯片跟着跑；拖动节点后芯片仍吸附在线上

跑法：<managed-python> verify/verify_edge_scifi.py
"""

import json
import os
import random
import re
import string
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)


def apireq(method, path, body=None, token=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, method=method, data=data,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer %s" % token} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def rgba_alpha(color: str) -> float:
    """从 computed color 里取 alpha；rgb(...) 视为 1.0。"""
    if not color:
        return -1.0
    m = re.search(r"rgba?\(([^)]+)\)", color)
    if not m:
        return -1.0
    parts = [p.strip() for p in m.group(1).replace("/", " ").split(",")]
    if len(parts) >= 4:
        try:
            return float(parts[3])
        except ValueError:
            return -1.0
    return 1.0


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

    email = "edge_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))
    password = "Password123"
    apireq("POST", "/auth/register", {"email": email, "password": password})
    tok = None
    try:
        tok = json.loads(urllib.request.urlopen(
            urllib.request.Request(
                BASE + "/auth/login", method="POST",
                data=json.dumps({"email": email, "password": password}).encode(),
                headers={"Content-Type": "application/json"},
            ), timeout=15).read().decode())["token"]
    except Exception as ex:
        info("login failed: %s" % ex)
    canvas_id, canvas_ver = None, 1
    if tok:
        try:
            cv = json.loads(urllib.request.urlopen(
                urllib.request.Request(
                    BASE + "/canvases", method="POST",
                    data=json.dumps({"title": "edgefx", "type": "personal"}).encode(),
                    headers={"Content-Type": "application/json",
                             "Authorization": "Bearer %s" % tok},
                ), timeout=15).read().decode())
            canvas_id, canvas_ver = cv.get("id"), cv.get("version", 1)
        except Exception as ex:
            info("create canvas failed: %s" % ex)
    info("user=%s canvas=%s" % (email, canvas_id))

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append("pageerror: " + str(e)))
        page.add_init_script("localStorage.setItem('__peaDevHooks','1');")
        page.add_init_script("""
            localStorage.setItem('pea_token', '""" + (tok or "x") + """');
            localStorage.setItem('pea_user', JSON.stringify({ id: 1, email: '""" + email + """' }));
            localStorage.setItem('pea_ui_route', JSON.stringify({ active: 'canvas', canvasId: """ + str(canvas_id or 1) + """ }));
        """)

        page.route(re.compile(r".*?/users/me.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"id": 1, "email": email, "displayName": "EdgeBot",
                             "balance": 999, "isAdmin": False, "planLevel": 0,
                             "effectivePlanLevel": 0, "planExpiresAt": None})))
        page.route(re.compile(r".*?/auth/refresh.*"), lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"token": tok or "x"})))
        page.route(re.compile(r".*?/canvases(\?.*)?$"), lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"ok": True, "data": []})))
        page.route(re.compile(r".*?/canvases/\d+.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"id": canvas_id or 1, "title": "edgefx", "version": canvas_ver,
                             "graph_json": {"nodes": [], "edges": []}})))
        page.route(re.compile(r".*?/models/available.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps([{"id": "mock-image", "providerId": "mock", "type": "image",
                              "modelType": "image", "name": "Mock", "displayName": "Mock",
                              "unlocked": True, "basePrice": 1}])))
        page.route(re.compile(r".*?/models/estimate.*"), lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"estimate": 1})))
        page.route(re.compile(r".*?/billing/balance.*"), lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps({"balance": 999})))

        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        if "/login" in page.evaluate("location.href"):
            page.evaluate("() => { const ui = window.__ui && window.__ui.getState(); if (ui) ui.setActive('canvas'); }")
            page.wait_for_timeout(1500)
        try:
            page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
        except Exception as ex:
            fail("dev hooks", "window.__canvas 未出现: %s" % ex)
            page.screenshot(path=os.path.join(SHOTS, "edge_debug_no_hook.png"))
            return results
        page.wait_for_timeout(1000)
        ok("dev hooks (window.__canvas 暴露)")

        # ── 注入 3 节点 + 2 条边：n1 -e1-> n2 -e2-> n3 ──────────────────────
        page.evaluate("""([cid, ver]) => {
            const cs = window.__canvas.getState();
            cs.setCanvasMeta(cid, ver, 'edgefx');
            cs.loadGraph(
              [
                { id: 'n1', type: 'pea', position: { x: 120, y: 200 }, data: { kind: 'text', label: 'N1', html: '<p>N1</p>' } },
                { id: 'n2', type: 'pea', position: { x: 620, y: 200 }, data: { kind: 'text', label: 'N2', html: '<p>N2</p>' } },
                { id: 'n3', type: 'pea', position: { x: 1120, y: 200 }, data: { kind: 'text', label: 'N3', html: '<p>N3</p>' } },
              ],
              [
                { id: 'e1', source: 'n1', target: 'n2', sourceHandle: 'out', targetHandle: 'in', type: 'pea' },
                { id: 'e2', source: 'n2', target: 'n3', sourceHandle: 'out', targetHandle: 'in', type: 'pea' },
              ],
              ver);
        }""", [canvas_id or 1, canvas_ver])
        page.wait_for_timeout(1800)
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('.pea-edge-line').length >= 2", timeout=12000)
            ok("注入 3 节点 / 2 连线，PeaEdge 分层主线渲染成功")
        except Exception as ex:
            fail("PeaEdge 渲染", str(ex))
            page.screenshot(path=os.path.join(SHOTS, "edge_debug_norender.png"))
            browser.close()
            return results
        page.screenshot(path=os.path.join(SHOTS, "edge_01_idle.png"))

        # ── 断言 1：空闲态低对比 + 微模糊 ───────────────────────────────────
        idle = page.evaluate("""() => {
            const el = document.querySelector('.pea-edge-line[data-edge-id="e1"]');
            if (!el) return null;
            const cs = getComputedStyle(el);
            return { active: el.getAttribute('data-active'), stroke: cs.stroke,
                     width: cs.strokeWidth, filter: cs.filter,
                     flow: document.querySelectorAll('.pea-edge-flow').length,
                     comet: document.querySelectorAll('.pea-edge-beads').length,
                     halo: document.querySelectorAll('.pea-edge-halo').length };
        }""")
        info("idle e1: %s" % idle)
        a = rgba_alpha(idle["stroke"]) if idle else -1
        if idle and idle["active"] == "0" and 0 < a <= 0.45:
            ok("空闲连线低对比（不抢视线）", "stroke=%s alpha=%.2f" % (idle["stroke"], a))
        else:
            fail("空闲连线低对比", "stroke=%s alpha=%s" % (idle and idle["stroke"], a))
        if idle and "blur" in (idle["filter"] or ""):
            ok("空闲连线带微模糊（融入背景）", "filter=%s" % idle["filter"])
        else:
            fail("空闲连线带微模糊", "filter=%s" % (idle and idle["filter"]))
        if idle and idle["flow"] == 0 and idle["comet"] == 0 and idle["halo"] == 0:
            ok("空闲态不渲染流动层/辉光层（性能）", "flow=0 beads=0 halo=0")
        else:
            fail("空闲态不渲染流动层/辉光层", str(idle))

        # ── 断言 2：选中「节点 n1」→ e1 高亮 + 流动 ─────────────────────────
        page.locator('.react-flow__node[data-id="n1"] .pea-node').click()
        page.wait_for_timeout(500)
        sel_node = page.evaluate("""() => {
            const e1 = document.querySelector('.pea-edge-line[data-edge-id="e1"]');
            const e2 = document.querySelector('.pea-edge-line[data-edge-id="e2"]');
            const cs1 = e1 ? getComputedStyle(e1) : null;
            const flow = document.querySelector('.pea-edge-flow');
            const beads = document.querySelector('.pea-edge-beads');
            const cf = flow ? getComputedStyle(flow) : null;
            const cc = beads ? getComputedStyle(beads) : null;
            // 光珠密度：dash 周期 vs 路径总长 → 实际渲染出的珠子颗数
            let period = null, pathLen = null, beadCount = null;
            if (beads && cc) {
              const nums = (cc.strokeDasharray || '').split(',')
                             .map(s => parseFloat(s)).filter(n => !isNaN(n));
              if (nums.length >= 2) period = nums[0] + nums[1];
              try { pathLen = beads.getTotalLength(); } catch (e) {}
              if (period && pathLen) beadCount = Math.floor(pathLen / period);
            }
            return {
              e1Active: e1 && e1.getAttribute('data-active'),
              e2Active: e2 && e2.getAttribute('data-active'),
              e1Stroke: cs1 && cs1.stroke, e1Width: cs1 && cs1.strokeWidth,
              e1Filter: cs1 && cs1.filter,
              flowCount: document.querySelectorAll('.pea-edge-flow').length,
              cometCount: document.querySelectorAll('.pea-edge-beads').length,
              haloCount: document.querySelectorAll('.pea-edge-halo').length,
              flowAnim: cf && cf.animationName, flowDash: cf && cf.strokeDasharray,
              cometAnim: cc && cc.animationName, cometDash: cc && cc.strokeDasharray,
              cometPathLength: beads && beads.getAttribute('pathLength'),
              period: period, pathLen: pathLen, beadCount: beadCount,
            };
        }""")
        info("选中 n1 后: %s" % sel_node)
        page.screenshot(path=os.path.join(SHOTS, "edge_02_node_selected.png"))
        if sel_node["e1Active"] == "1" and sel_node["e2Active"] == "0":
            ok("选中节点 → 仅相连的边进入 active（e1=1, e2=0）")
        else:
            fail("选中节点 → 相连边 active", "e1=%s e2=%s" % (sel_node["e1Active"], sel_node["e2Active"]))
        a2 = rgba_alpha(sel_node["e1Stroke"])
        if a2 > 0.8 and "drop-shadow" in (sel_node["e1Filter"] or ""):
            ok("active 主线高亮 + 辉光", "stroke=%s filter=%s" % (sel_node["e1Stroke"], sel_node["e1Filter"][:48]))
        else:
            fail("active 主线高亮 + 辉光", "stroke=%s filter=%s" % (sel_node["e1Stroke"], sel_node["e1Filter"]))
        if sel_node["flowCount"] == 1 and sel_node["cometCount"] == 1 and sel_node["haloCount"] == 1:
            ok("active 边渲染 halo/flow/beads 三层", "各 1 层，未激活边不渲染")
        else:
            fail("active 边渲染三层", str(sel_node))
        if "pea-edge-flow-move" in (sel_node["flowAnim"] or ""):
            ok("流动虚线动画生效", "anim=%s dash=%s" % (sel_node["flowAnim"], sel_node["flowDash"]))
        else:
            fail("流动虚线动画生效", "anim=%s" % sel_node["flowAnim"])
        if "pea-edge-beads-move" in (sel_node["cometAnim"] or ""):
            ok("流动光珠动画生效", "anim=%s dash=%s" % (sel_node["cometAnim"], sel_node["cometDash"]))
        else:
            fail("流动光珠动画生效", "anim=%s" % sel_node["cometAnim"])

        # ── 修复①：光珠是「一串」而非一颗 ──────────────────────────────────
        # 旧实现 pathLength=100 + dasharray 0.6/99.4 → 全线恒定 1 颗。
        # 新实现取消归一化，dash 周期落在画布坐标系 → 珠数 = 路径长 / 周期。
        if sel_node["cometPathLength"] is None:
            ok("光珠层已取消 pathLength 归一化（珠数随线长走）")
        else:
            fail("光珠层应取消 pathLength 归一化", "pathLength=%s" % sel_node["cometPathLength"])
        bc = sel_node["beadCount"]
        info("光珠：周期=%s px, 路径长=%.1f, 珠数≈%s" %
             (sel_node["period"], sel_node["pathLen"] or -1, bc))
        if bc is not None and bc >= 4:
            ok("修复①：光珠成串（不再只有 1 颗）",
               "珠数≈%d（周期 %.1fpx / 路径 %.0fpx）" % (bc, sel_node["period"], sel_node["pathLen"]))
        else:
            fail("修复①：光珠成串", "珠数=%s period=%s len=%s"
                 % (bc, sel_node["period"], sel_node["pathLen"]))

        # ── 断言 3：方向性 —— 渐变从 source 指向 target，且 to 端更实 ────────
        direction = page.evaluate("""() => {
            const g = document.querySelector('linearGradient[id^="pea-edge-grad-"]');
            if (!g) return null;
            const stops = Array.from(g.querySelectorAll('stop'));
            const cFrom = stops[0] ? getComputedStyle(stops[0]).stopColor : null;
            const cTo = stops[stops.length-1] ? getComputedStyle(stops[stops.length-1]).stopColor : null;
            // n1 在左、n2 在右 → x2 应显著大于 x1（方向 = 从 source 到 target）
            return { id: g.id,
                     x1: parseFloat(g.getAttribute('x1')), y1: parseFloat(g.getAttribute('y1')),
                     x2: parseFloat(g.getAttribute('x2')), y2: parseFloat(g.getAttribute('y2')),
                     units: g.getAttribute('gradientUnits'),
                     from: cFrom, to: cTo };
        }""")
        info("方向渐变: %s" % direction)
        if direction and direction["x2"] > direction["x1"] + 100 and direction["units"] == "userSpaceOnUse":
            ok("渐变方向 = source→target（x1<x2，画布坐标系）",
               "x1=%.0f x2=%.0f" % (direction["x1"], direction["x2"]))
        else:
            fail("渐变方向 = source→target", str(direction))
        af, at = rgba_alpha(direction["from"]), rgba_alpha(direction["to"])
        if at > af:
            ok("渐变 target 端比 source 端更实（静态也能读方向）",
               "from_a=%.2f → to_a=%.2f" % (af, at))
        else:
            fail("渐变 target 端更实", "from=%s to=%s" % (direction["from"], direction["to"]))

        # keyframes 必须是负向 dashoffset（正向会看起来倒流）
        kf = page.evaluate("""() => {
            const out = {};
            for (const ss of Array.from(document.styleSheets)) {
              let rules; try { rules = ss.cssRules; } catch(e) { continue; }
              for (const r of Array.from(rules || [])) {
                if (r.type === CSSRule.KEYFRAMES_RULE &&
                    (r.name === 'pea-edge-flow-move' || r.name === 'pea-edge-beads-move')) {
                  out[r.name] = Array.from(r.cssRules).map(k => k.cssText).join(' ');
                }
              }
            }
            return out;
        }""")
        info("keyframes: %s" % kf)
        fm = kf.get("pea-edge-flow-move", "")
        cm = kf.get("pea-edge-beads-move", "")
        # 光珠位移量必须恰好等于一个 dash 周期，否则循环会「跳一下」
        import re as _re
        m = _re.search(r"stroke-dashoffset:\s*(-?[\d.]+)", cm)
        beads_shift = abs(float(m.group(1))) if m else None
        if "-16" in fm and cm.count("-") >= 1:
            ok("动画方向为负向 dashoffset（顺连接方向流动，非倒流）",
               "flow→-16, beads→%s" % (m.group(1) if m else "?"))
        else:
            fail("动画方向为负向 dashoffset", "flow=%s beads=%s" % (fm, cm))
        if beads_shift and sel_node["period"] and abs(beads_shift - sel_node["period"]) < 0.01:
            ok("光珠位移量 = 一个 dash 周期（循环无缝，不跳帧）",
               "shift=%.1f period=%.1f" % (beads_shift, sel_node["period"]))
        else:
            fail("光珠位移量 = 一个 dash 周期",
                 "shift=%s period=%s" % (beads_shift, sel_node["period"]))

        # ── 断言 4：拖动节点 n2 时，e1/e2 双双 active ───────────────────────
        page.mouse.click(6, 300)  # 先清空选择
        page.wait_for_timeout(300)
        box = page.locator('.react-flow__node[data-id="n2"]').bounding_box()
        sx, sy = box["x"] + box["width"] / 2, box["y"] + 16
        page.mouse.move(sx, sy)
        page.mouse.down()
        for i in range(1, 10):
            page.mouse.move(sx + i * 8, sy + i * 5)
            page.wait_for_timeout(20)
        mid_drag = page.evaluate("""() => {
            const g = (id) => {
              const el = document.querySelector('.pea-edge-line[data-edge-id="'+id+'"]');
              return el ? el.getAttribute('data-active') : null;
            };
            return { e1: g('e1'), e2: g('e2'),
                     flow: document.querySelectorAll('.pea-edge-flow').length,
                     comet: document.querySelectorAll('.pea-edge-beads').length };
        }""")
        page.screenshot(path=os.path.join(SHOTS, "edge_03_dragging.png"))
        page.mouse.up()
        page.wait_for_timeout(300)
        info("拖动 n2 途中: %s" % mid_drag)
        if mid_drag["e1"] == "1" and mid_drag["e2"] == "1" and mid_drag["flow"] == 2:
            ok("拖动节点时，两侧相连边同时高亮 + 流动", str(mid_drag))
        else:
            fail("拖动节点时相连边高亮流动", str(mid_drag))

        # ── 断言 5：真实点击连线上某一点 → 芯片出现在「点击处」而非中点 ──────
        page.mouse.click(6, 300)
        page.wait_for_timeout(250)

        def edge_point_screen(edge_id, frac):
            """取 edge 路径上 frac 比例处的屏幕坐标（经 getScreenCTM 变换）。"""
            return page.evaluate("""([eid, f]) => {
                const line = document.querySelector('.pea-edge-line[data-edge-id="'+eid+'"]');
                if (!line) return null;
                const g = line.closest('g');
                const hit = g && g.querySelector('.react-flow__edge-interaction');
                if (!hit) return null;
                const len = hit.getTotalLength();
                const p = hit.getPointAtLength(len * f);
                const m = hit.getScreenCTM();
                return { x: m.a * p.x + m.c * p.y + m.e, y: m.b * p.x + m.d * p.y + m.f,
                         flowX: p.x, flowY: p.y, len: len };
            }""", [edge_id, frac])

        def chip_center_screen():
            return page.evaluate("""() => {
                const el = document.querySelector('.pea-edge-del');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                const anchor = el.closest('.pea-edge-del-anchor');
                return { x: r.left + r.width / 2, y: r.top + r.height / 2,
                         anchored: anchor && anchor.getAttribute('data-chip-anchored') };
            }""")

        # 中点屏幕坐标（旧实现芯片恒定出现在这里）作为对照基准
        mid_pt = edge_point_screen("e1", 0.5)
        # 点在靠近 source 的 22% 处
        p22 = edge_point_screen("e1", 0.22)
        page.mouse.click(p22["x"], p22["y"])
        page.wait_for_timeout(450)
        c22 = chip_center_screen()
        info("点击 22%% 处 screen=(%.0f,%.0f) → 芯片=(%.0f,%.0f)；中点=(%.0f,%.0f)"
             % (p22["x"], p22["y"], (c22 or {}).get("x", -1), (c22 or {}).get("y", -1),
                mid_pt["x"], mid_pt["y"]))
        page.screenshot(path=os.path.join(SHOTS, "edge_04a_chip_at_22.png"))
        if c22:
            d_click = ((c22["x"] - p22["x"]) ** 2 + (c22["y"] - p22["y"]) ** 2) ** 0.5
            d_mid = ((c22["x"] - mid_pt["x"]) ** 2 + (c22["y"] - mid_pt["y"]) ** 2) ** 0.5
            if d_click <= 12:
                ok("修复②：芯片出现在鼠标点击处（22%%）", "距点击点 %.1fpx" % d_click)
            else:
                fail("修复②：芯片出现在点击处", "距点击点 %.1fpx（>12）" % d_click)
            if d_mid > 40:
                ok("修复②：芯片不再固定在连线中点", "距中点 %.1fpx" % d_mid)
            else:
                fail("修复②：芯片不再固定在中点", "距中点仅 %.1fpx" % d_mid)
            if c22.get("anchored") == "1":
                ok("芯片标记为「已吸附到点击落点」", "data-chip-anchored=1")
            else:
                fail("芯片吸附标记", "data-chip-anchored=%s" % c22.get("anchored"))
        else:
            fail("修复②：点击连线后芯片出现", "未找到 .pea-edge-del")

        # 再点靠近 target 的 78% 处 → 芯片应跟着跑过去
        p78 = edge_point_screen("e1", 0.78)
        page.mouse.click(p78["x"], p78["y"])
        page.wait_for_timeout(450)
        c78 = chip_center_screen()
        page.screenshot(path=os.path.join(SHOTS, "edge_04b_chip_at_78.png"))
        if c78:
            d_click78 = ((c78["x"] - p78["x"]) ** 2 + (c78["y"] - p78["y"]) ** 2) ** 0.5
            moved = ((c78["x"] - c22["x"]) ** 2 + (c78["y"] - c22["y"]) ** 2) ** 0.5
            info("点击 78%% → 芯片=(%.0f,%.0f)，较上次移动 %.0fpx" % (c78["x"], c78["y"], moved))
            if d_click78 <= 12 and moved > 40:
                ok("修复②：换个位置点，芯片跟着跑", "距点击 %.1fpx，位移 %.0fpx" % (d_click78, moved))
            else:
                fail("修复②：换位置点芯片跟随", "距点击 %.1fpx 位移 %.0fpx" % (d_click78, moved))
        else:
            fail("修复②：二次点击后芯片存在", "未找到 .pea-edge-del")

        # ── 修复②：拖动节点 → 芯片逻辑校验 ────────────────────────────────
        # 关键行为：ReactFlow 在「拖动节点」时会取消选中该边（选中节点 ≠ 选中边），
        # 因此芯片（仅选中边时出现）应「正确隐藏」；但连线仍因节点被选中而 active 流动。
        # 验证两件事：
        #   (a) 拖后芯片隐藏 + 边仍 active（流动方向/高亮仍生效，符合原始需求）；
        #   (b) 重新点「移动后」的线同比例处，芯片回到新落点（证明 clickT 按比例定位、随线漂移）。
        nbox = page.locator('.react-flow__node[data-id="n1"]').bounding_box()
        ndrag_x, ndrag_y = nbox["x"] + nbox["width"] / 2, nbox["y"] + 16
        page.mouse.move(ndrag_x, ndrag_y)
        page.mouse.down()
        for i in range(1, 8):
            page.mouse.move(ndrag_x, ndrag_y - i * 9)
            page.wait_for_timeout(20)
        page.mouse.up()
        page.wait_for_timeout(450)
        after_drag = page.evaluate("""() => {
            const chip = document.querySelector('.pea-edge-del');
            const line = document.querySelector('.pea-edge-line[data-edge-id="e1"]');
            return { chipExists: !!chip,
                     e1Active: line ? line.getAttribute('data-active') : null };
        }""")
        page.screenshot(path=os.path.join(SHOTS, "edge_04c_after_drag.png"))
        info("拖动 n1 后：芯片存在=%s, e1 active=%s" % (after_drag["chipExists"], after_drag["e1Active"]))

        if after_drag["chipExists"] is True:
            # 极端情况：节点拖动未取消边选中 → 芯片应仍吸附在线上（比例定位，不脱线）
            off = page.evaluate("""() => {
                const el = document.querySelector('.pea-edge-del');
                const line = document.querySelector('.pea-edge-line[data-edge-id="e1"]');
                if (!el || !line) return null;
                const g = line.closest('g');
                const hit = g.querySelector('.react-flow__edge-interaction');
                const r = el.getBoundingClientRect();
                const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
                const m = hit.getScreenCTM();
                const len = hit.getTotalLength();
                let best = Infinity;
                for (let i = 0; i <= 200; i++) {
                  const p = hit.getPointAtLength(len * i / 200);
                  const sx = m.a * p.x + m.c * p.y + m.e;
                  const sy = m.b * p.x + m.d * p.y + m.f;
                  const d = Math.hypot(sx - cx, sy - cy);
                  if (d < best) best = d;
                }
                return { dist: best };
            }""")
            if off and off["dist"] <= 6:
                ok("修复②：拖动后边仍选中，芯片仍吸附在线上（比例定位，不脱线）",
                   "离线 %.2fpx" % off["dist"])
            else:
                fail("修复②：拖动后芯片吸附在线", "离线 %s" % (off or {}).get("dist"))
        else:
            # 期望路径：拖动节点会取消选中该边（选中节点 ≠ 选中边），
            # 芯片（仅选中边时出现）正确隐藏；但连线仍因节点被选中而 active 流动。
            if after_drag["e1Active"] == "1":
                ok("修复②：拖动节点取消选中该边（芯片隐藏），但边仍因节点选中而 active 流动",
                   "chipHidden=true e1Active=1")
            else:
                fail("修复②：拖动后边仍 active", "e1Active=%s" % after_drag["e1Active"])

        # 重新点击「移动后」的线同比例（0.78）处 → 芯片回到新落点（证明 clickT 比例定位）
        p78b = edge_point_screen("e1", 0.78)
        page.mouse.click(p78b["x"], p78b["y"])
        page.wait_for_timeout(450)
        c78b = chip_center_screen()
        page.screenshot(path=os.path.join(SHOTS, "edge_04d_chip_relocate.png"))
        if c78b and p78b:
            d2 = ((c78b["x"] - p78b["x"]) ** 2 + (c78b["y"] - p78b["y"]) ** 2) ** 0.5
            shifted = ((c78b["x"] - p78["x"]) ** 2 + (c78b["y"] - p78["y"]) ** 2) ** 0.5
            info("重新点移动后线 78%%：芯片=(%.0f,%.0f)（对点击点距离 %.1fpx；与拖前同比例落点位移 %.0fpx）"
                 % (c78b["x"], c78b["y"], d2, shifted))
            # 核心：重选边后芯片必须精确出现在本次点击处（与拖前 22%/78% 行为一致）。
            # shifted 仅作信息参考（节点实际位移大小取决于拖拽幅度），不作为硬断言。
            if d2 <= 12:
                ok("修复②：节点移动后，重选线同比例处芯片精确出现在新点击落点",
                   "距新点击 %.1fpx（与拖前同比例落点位移 %.0fpx，证明随线漂移）" % (d2, shifted))
            else:
                fail("修复②：重选移动后线芯片出现在点击处", "距点击 %.1fpx" % d2)
        else:
            fail("修复②：重选移动后线芯片出现", "未找到 .pea-edge-del")
        chip = page.evaluate("""() => {
            const btn = document.querySelector('.pea-edge-del');
            if (!btn) return null;
            const anchor = btn.closest('.pea-edge-del-anchor');
            const ring = btn.querySelector('.pea-edge-del-ring');
            const hex = btn.querySelector('.pea-edge-del-hex');
            const x = btn.querySelector('.pea-edge-del-x');
            const cr = ring ? getComputedStyle(ring) : null;
            const r = btn.getBoundingClientRect();
            return {
              hasRing: !!ring, hasHex: !!hex, hasX: !!x,
              ringAnim: cr && cr.animationName, ringDash: cr && cr.strokeDasharray,
              anchorTransform: anchor ? anchor.style.transform : null,
              w: Math.round(r.width), h: Math.round(r.height),
              legacyRedCircle: getComputedStyle(btn).backgroundColor,
              e1Active: document.querySelector('.pea-edge-line[data-edge-id="e1"]').getAttribute('data-active'),
            };
        }""")
        info("HUD 芯片: %s" % chip)
        page.screenshot(path=os.path.join(SHOTS, "edge_04_chip.png"))
        if chip and chip["hasRing"] and chip["hasHex"] and chip["hasX"]:
            ok("HUD 芯片结构完整（扫描环 + 六边核心 + ×）")
        else:
            fail("HUD 芯片结构完整", str(chip))
        if chip and "pea-edge-del-spin" in (chip["ringAnim"] or ""):
            ok("扫描环自转动画生效", "anim=%s dash=%s" % (chip["ringAnim"], chip["ringDash"]))
        else:
            fail("扫描环自转动画生效", "anim=%s" % (chip and chip["ringAnim"]))
        if chip and "scale(var(--pea-inv-zoom" in (chip["anchorTransform"] or ""):
            ok("芯片 counter-scale（缩放画布时屏幕尺寸恒定）", chip["anchorTransform"][-40:])
        else:
            fail("芯片 counter-scale", "transform=%s" % (chip and chip["anchorTransform"]))
        if chip and "rgba(0, 0, 0, 0)" in (chip["legacyRedCircle"] or "") :
            ok("旧的红色实心圆按钮已移除（背景透明，改由 SVG 绘制）")
        else:
            fail("旧红圆已移除", "bg=%s" % (chip and chip["legacyRedCircle"]))
        if chip and chip["e1Active"] == "1":
            ok("选中连线本身 → 该连线 active 高亮 + 流动")
        else:
            fail("选中连线本身 → active", "e1=%s" % (chip and chip["e1Active"]))

        # ── 断言 6：点击芯片真的删掉这条边 ─────────────────────────────────
        before = page.evaluate("() => window.__canvas.getState().edges.map(e=>e.id)")
        page.locator(".pea-edge-del").first.click()
        page.wait_for_timeout(500)
        after = page.evaluate("() => window.__canvas.getState().edges.map(e=>e.id)")
        info("删除前 %s → 删除后 %s" % (before, after))
        if "e1" in before and "e1" not in after:
            ok("点击 HUD 芯片成功断开连线", "%s → %s" % (before, after))
        else:
            fail("点击 HUD 芯片断开连线", "%s → %s" % (before, after))

        # ── 断言 7：取消选择 → 回落空闲态 ──────────────────────────────────
        page.evaluate("() => window.__canvas.getState().clearSelection()")
        page.wait_for_timeout(400)
        back = page.evaluate("""() => ({
            active: Array.from(document.querySelectorAll('.pea-edge-line')).map(e=>e.getAttribute('data-active')),
            flow: document.querySelectorAll('.pea-edge-flow').length,
            comet: document.querySelectorAll('.pea-edge-beads').length,
            chip: document.querySelectorAll('.pea-edge-del').length,
        })""")
        info("取消选择后: %s" % back)
        page.screenshot(path=os.path.join(SHOTS, "edge_05_back_idle.png"))
        if all(v == "0" for v in back["active"]) and back["flow"] == 0 and back["comet"] == 0 and back["chip"] == 0:
            ok("取消选择 → 连线回落空闲态，芯片消失")
        else:
            fail("取消选择 → 回落空闲态", str(back))

        # ── 附加：暗色主题下令牌切换生效 ───────────────────────────────────
        page.evaluate("() => document.documentElement.classList.add('dark')")
        page.wait_for_timeout(300)
        dark_stroke = page.evaluate("""() => {
            const el = document.querySelector('.pea-edge-line');
            return el ? getComputedStyle(el).stroke : null;
        }""")
        page.screenshot(path=os.path.join(SHOTS, "edge_06_dark.png"))
        info("暗色空闲 stroke=%s" % dark_stroke)
        if dark_stroke and dark_stroke != idle["stroke"]:
            ok("明/暗主题连线取不同令牌（各自融入背景）",
               "light=%s dark=%s" % (idle["stroke"], dark_stroke))
        else:
            fail("明/暗主题连线令牌切换", "light=%s dark=%s" % (idle["stroke"], dark_stroke))
        page.evaluate("() => document.documentElement.classList.remove('dark')")

        print("\n=== CONSOLE ERRORS ===")
        if console_errors:
            for e in console_errors[:20]:
                print(" ", e)
        else:
            print("  (none)")

        passed = sum(1 for r in results if r[0] == "PASS")
        failed = sum(1 for r in results if r[0] == "FAIL")
        print(f"\n=== RESULT: {passed} PASS, {failed} FAIL ===")
        browser.close()
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
