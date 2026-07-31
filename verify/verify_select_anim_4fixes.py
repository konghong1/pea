"""验证画布交互四个修复：
  1. 节点拖拽不再生硬（.pea-node 上没有 transform 过渡，hover 也不上浮 -2px）
  2. 单选时不再画 .pea-selection-bounds 外框（只有节点自身 ring）
  3. 多选时仍画 .pea-selection-bounds 外框（包住所有选中节点）
  4. 选中态有 ring + ripple 动画（box-shadow 包含 0 0 0 1.5px brand + glow + animation）

通过 API 注册+建画布，init_script 注入 token/route/hooks，mock /models，
注入节点后用真实点击 / Shift+点击 / 拖拽触发交互，再读 computed style 验证。
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

    email = "sel4f_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))
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
    canvas_id = None
    canvas_ver = 1
    if tok:
        try:
            cv = json.loads(urllib.request.urlopen(
                urllib.request.Request(
                    BASE + "/canvases", method="POST",
                    data=json.dumps({"title": "sel4fix", "type": "personal"}).encode(),
                    headers={"Content-Type": "application/json",
                             "Authorization": "Bearer %s" % tok},
                ), timeout=15).read().decode())
            canvas_id = cv.get("id")
            canvas_ver = cv.get("version", 1)
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
        page.on("response", lambda r: info("[resp %d] %s" % (r.status, r.url)) if r.status >= 400 and "/api/" not in r.url else None)
        page.add_init_script("localStorage.setItem('__peaDevHooks','1');")

        page.add_init_script("""
            localStorage.setItem('pea_token', ' """ + (tok or "x") + """ ');
            localStorage.setItem('pea_user', JSON.stringify({ id: 1, email: ' """ + email + """ ' }));
            localStorage.setItem('pea_ui_route', JSON.stringify({ active: 'canvas', canvasId: """ + str(canvas_id or 1) + """ }));
        """)

        # Mock 所有画布需要的 API（避免 401 清 token）
        page.route(re.compile(r".*?/users/me.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"id": 1, "email": email, "displayName": "SelBot",
                             "balance": 999, "isAdmin": False, "planLevel": 0,
                             "effectivePlanLevel": 0, "planExpiresAt": None})))
        page.route(re.compile(r".*?/auth/refresh.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"token": tok or "x"})))
        page.route(re.compile(r".*?/canvases(\?.*)?$"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "data": []})))
        page.route(re.compile(r".*?/canvases/\d+.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"id": canvas_id or 1, "title": "sel4fix", "version": canvas_ver,
                             "graph_json": {"nodes": [], "edges": []}})))
        page.route(re.compile(r".*?/models/available.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps([
                {"id": "mock-image", "providerId": "mock", "type": "image",
                 "modelType": "image", "name": "Mock Image", "displayName": "Mock Image",
                 "unlocked": True, "basePrice": 1}
            ])))
        page.route(re.compile(r".*?/models/estimate.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"estimate": 1})))
        page.route(re.compile(r".*?/billing/balance.*"), lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"balance": 999})))

        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        if "/login" in page.evaluate("location.href"):
            page.evaluate("""() => { const ui = window.__ui && window.__ui.getState(); if (ui) ui.setActive('canvas'); }""")
            page.wait_for_timeout(1500)
        try:
            page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
        except Exception as ex:
            fail("dev hooks", "window.__canvas 未出现: %s" % ex)
            page.screenshot(path=os.path.join(SHOTS, "debug_no_hook.png"))
            return results
        page.wait_for_timeout(1200)
        ok("dev hooks (window.__canvas 暴露)")

        # ── 1. 注入 2 个文本节点（避开 text-node 工具条，先用 text）──
        page.evaluate("""([cid, ver]) => {
            const cs = window.__canvas.getState();
            cs.setCanvasMeta(cid, ver, 'sel4fix');
            cs.loadGraph([
              { id: 'n1', type: 'pea', position: { x: 240, y: 240 }, data: { kind: 'text', label: 'N1', html: '<p>N1</p>' } },
              { id: 'n2', type: 'pea', position: { x: 720, y: 240 }, data: { kind: 'text', label: 'N2', html: '<p>N2</p>' } },
            ], [], ver);
        }""", [canvas_id or 1, canvas_ver])
        page.wait_for_timeout(2000)
        page.wait_for_function("""() => {
            const ns = document.querySelectorAll('.react-flow__node[data-id]');
            return ns.length >= 2 && Array.from(ns).every(n => n.getBoundingClientRect().width > 0);
        }""", timeout=12000)
        ok("注入 2 节点")
        page.screenshot(path=os.path.join(SHOTS, "sel4_01_loaded.png"))

        # ── 2. 关键断言 1：.pea-node 上 transition-property 不含 transform ──
        node_style = page.evaluate("""() => {
            const n = document.querySelector('.react-flow__node[data-id=\"n1\"] .pea-node');
            if (!n) return null;
            const cs = getComputedStyle(n);
            return { transitionProperty: cs.transitionProperty, transform: cs.transform };
        }""")
        info(".pea-node computed: %s" % node_style)
        if node_style and "transform" not in node_style["transitionProperty"]:
            ok("修复1a：.pea-node transition 不含 transform", "trans=%s" % node_style["transitionProperty"])
        else:
            fail("修复1a：.pea-node transition 不含 transform", "trans=%s" % node_style)

        # ── 3. 关键断言 2：.pea-node:hover 不会有 translateY(-2px) ──
        page.evaluate("""() => {
            const n = document.querySelector('.react-flow__node[data-id=\"n1\"] .pea-node');
            if (!n) return;
            // 强制触发 :hover 状态（用伪类 :hover 没法直接读，改用 dispatchEvent 模拟）
            const rect = n.getBoundingClientRect();
            const ev = new MouseEvent('mouseenter', { bubbles: true, clientX: rect.left + 10, clientY: rect.top + 10 });
            n.dispatchEvent(ev);
            const ev2 = new MouseEvent('mouseover', { bubbles: true, clientX: rect.left + 10, clientY: rect.top + 10 });
            n.dispatchEvent(ev2);
        }""")
        # 真实 hover：用鼠标移到节点上
        box = page.locator('.react-flow__node[data-id="n1"]').bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(300)
        hover_style = page.evaluate("""() => {
            const n = document.querySelector('.react-flow__node[data-id=\"n1\"] .pea-node');
            if (!n) return null;
            return getComputedStyle(n).transform;
        }""")
        info(".pea-node hover transform: %s" % hover_style)
        # matrix(1,0,0,1,0,0) 或 none 都是无 translate；只要不是 "0, -2" 就 ok
        if hover_style and "0, -2" not in hover_style:
            ok("修复1b：hover 时无 translateY(-2px)", "transform=%s" % hover_style)
        else:
            fail("修复1b：hover 时无 translateY(-2px)", "transform=%s" % hover_style)

        # ── 4. 单击 n1：单选 ──
        page.locator('.react-flow__node[data-id="n1"] .pea-node').click()
        page.wait_for_timeout(700)  # 等 ripple 动画跑一段
        page.screenshot(path=os.path.join(SHOTS, "sel4_02_single.png"))

        # ── 5. 关键断言 3：单选时 body 上不应有 .pea-selection-bounds ──
        bc_single = page.locator("body > .pea-selection-bounds").count()
        info("单选时 .pea-selection-bounds 数量: %d" % bc_single)
        if bc_single == 0:
            ok("修复2：单选时无 .pea-selection-bounds 外框")
        else:
            fail("修复2：单选时无 .pea-selection-bounds 外框", "实际=%d" % bc_single)

        # ── 6. 关键断言 4：单选时 body-card 应有 ring box-shadow + animation ──
        bc_style = page.evaluate("""() => {
            const c = document.querySelector('.react-flow__node[data-id=\"n1\"] .pea-node-body-card');
            if (!c) return null;
            const cs = getComputedStyle(c);
            return { boxShadow: cs.boxShadow, borderColor: cs.borderColor,
                     animationName: cs.animationName, animationDuration: cs.animationDuration };
        }""")
        info("body-card style: %s" % bc_style)
        # 关键特征：box-shadow 含 1.5px 的 ring（brand 色实际解析为 rgb(31,162,220)=#1fa2dc，
        # 不是 fallback 的 #38e1ff，因此断言只看 ring 的 1.5px 像素宽度，避免写死颜色）。
        # 完整 ring 形如：rgb(31, 162, 220) 0px 0px 0px 1.5px, rgba(56,225,255,0.28) 0px 0px 18px 0px, ...
        has_ring = bc_style and "1.5px" in bc_style["boxShadow"]
        has_anim = bc_style and "pea-node-select" in (bc_style["animationName"] or "")
        if has_ring:
            ok("修复3a：body-card 有 ring box-shadow (1.5px brand)", "shadow=%s" % bc_style["boxShadow"][:80])
        else:
            fail("修复3a：body-card 有 ring box-shadow (1.5px brand)", "shadow=%s" % bc_style)
        if has_anim:
            ok("修复3b：body-card 有 pea-node-select 动画", "anim=%s" % bc_style["animationName"])
        else:
            fail("修复3b：body-card 有 pea-node-select 动画", "anim=%s" % bc_style.get("animationName"))

        # ── 7. 加选 n2：真实 Shift+点击 多选（修复后应为 >=2）──
        page.locator('.react-flow__node[data-id="n2"] .pea-node').click(modifiers=["Shift"])
        page.wait_for_timeout(400)
        real_sel = page.evaluate("() => window.__canvas.getState().selectedIds.slice()")
        info("真实 Shift+点击 n2 后 selectedIds=%s" % real_sel)
        if len(real_sel) >= 2:
            ok("修复5：真实 Shift+点击 触发多选", "ids=%s" % real_sel)
        else:
            fail("修复5：真实 Shift+点击 触发多选", "ids=%s" % real_sel)

        # ── 8. 关键断言 5：多选（>=2）时 body 上应有 .pea-selection-bounds ──
        # 用 store.setSelection 直接驱动到确定的「多选」状态做确定性验证，
        # 避免 Playwright Shift+点击在不同环境下偶发不触发多选取导致的假阴性。
        page.evaluate("() => window.__canvas.getState().setSelection(['n1','n2'])")
        page.wait_for_timeout(500)
        bc_multi = page.locator("body > .pea-selection-bounds").count()
        info("多选时 .pea-selection-bounds 数量: %d" % bc_multi)
        page.screenshot(path=os.path.join(SHOTS, "sel4_03_multi.png"))
        if bc_multi >= 1:
            ok("修复4：多选时 .pea-selection-bounds 外框出现", "count=%d" % bc_multi)
        else:
            fail("修复4：多选时 .pea-selection-bounds 外框出现", "实际=%d" % bc_multi)
        # 诊断：真实 Shift+点击是否真的产生多选（不影响主断言，仅记录）
        info("诊断：真实 Shift+点击 selectedIds=%s（修复5 已使其多选）" % real_sel)

        # ── 8b. 真实「框选」(在空白 pane 上拖拽) 多选取：验证主交互路径下 bounds 也出现 ──
        # 本应用的多选取主要路径是 selectionOnDrag + selectionMode=Partial 的框选，
        # 而非 Shift+点击（ReactFlow 的 selectionKeyCode 默认是 Shift，会与 Shift+点击冲突）。
        # 因此这里用真实拖拽框选两个节点，确认 fix4 在真实交互下同样成立。
        page.mouse.click(5, 5)  # 点空白清选择
        page.wait_for_timeout(200)
        rects = page.evaluate("""() => {
            const out = {};
            for (const id of ['n1','n2']) {
                const el = document.querySelector('.react-flow__node[data-id="'+id+'"]');
                const r = el.getBoundingClientRect();
                out[id] = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
            }
            return out;
        }""")
        minL = min(rects['n1']['left'], rects['n2']['left']) - 40
        minT = min(rects['n1']['top'], rects['n2']['top']) - 40
        maxR = max(rects['n1']['right'], rects['n2']['right']) + 40
        maxB = max(rects['n1']['bottom'], rects['n2']['bottom']) + 40
        page.mouse.move(minL, minT)
        page.mouse.down()
        for i in range(1, 16):
            page.mouse.move(minL + (maxR - minL) * i / 15, minT + (maxB - minT) * i / 15)
            page.wait_for_timeout(15)
        page.mouse.up()
        page.wait_for_timeout(500)
        box_sel = page.evaluate("() => window.__canvas.getState().selectedIds.slice()")
        info("真实框选后 selectedIds=%s" % box_sel)
        bc_box = page.locator("body > .pea-selection-bounds").count()
        info("真实框选多选取时 .pea-selection-bounds 数量: %d" % bc_box)
        page.screenshot(path=os.path.join(SHOTS, "sel4_03b_boxsel.png"))
        if len(box_sel) >= 2 and bc_box >= 1:
            ok("修复4b：真实框选产生多选且 bounds 出现", "ids=%s count=%d" % (box_sel, bc_box))
        else:
            fail("修复4b：真实框选产生多选且 bounds 出现", "ids=%s count=%d" % (box_sel, bc_box))

        # ── 9. 拖拽验证：n1 拖到一个明显的新位置 ──
        before_pos = page.evaluate("() => window.__canvas.getState().nodes.find(n=>n.id==='n1').position")
        page.locator('.react-flow__node[data-id="n1"] .pea-node').click()  # 先确保单选
        page.wait_for_timeout(300)
        box = page.locator('.react-flow__node[data-id="n1"]').bounding_box()
        sx = box["x"] + box["width"] / 2
        sy = box["y"] + box["height"] / 2
        # 真实拖拽：mousedown → 多次 mousemove → mouseup
        page.mouse.move(sx, sy)
        page.mouse.down()
        for i in range(1, 16):
            page.mouse.move(sx + i * 12, sy + i * 6)
            page.wait_for_timeout(15)
        page.mouse.up()
        page.wait_for_timeout(400)
        after_pos = page.evaluate("() => window.__canvas.getState().nodes.find(n=>n.id==='n1').position")
        info("n1 拖拽 before=%s after=%s" % (before_pos, after_pos))
        moved_x = after_pos["x"] - before_pos["x"]
        moved_y = after_pos["y"] - before_pos["y"]
        if abs(moved_x) > 50 and abs(moved_y) > 30:
            ok("修复1c：拖拽后位置正确变化 (dx=%.0f dy=%.0f)" % (moved_x, moved_y))
        else:
            fail("修复1c：拖拽后位置正确变化", "dx=%.0f dy=%.0f" % (moved_x, moved_y))
        page.screenshot(path=os.path.join(SHOTS, "sel4_04_after_drag.png"))

        print("\n=== CONSOLE ERRORS ===")
        if console_errors:
            for e in console_errors[:20]:
                print(" ", e)
        else:
            print("  (none)")

        # 总结
        passed = sum(1 for r in results if r[0] == "PASS")
        failed = sum(1 for r in results if r[0] == "FAIL")
        print(f"\n=== RESULT: {passed} PASS, {failed} FAIL ===")
        browser.close()
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
