"""
E2E 验证：打组 UI 三项修复（2026-07-31）
  1) 组名显示在打组框左上角，无图标；工具条不再显示组名。
  2) 背景切换按钮改成色块+文字"切换背景"，点击展开圆点色板并可切换组背景色。
  3) 解组后组容器与选择框同时消失，选中态清空。

通过 window.__canvas 注入节点 + 真实打组 + DOM 测量。
需要 localStorage.__peaDevHooks=1 + window.__canvas（DEV 模式或该 flag）。
"""
import json
import os
import sys
import time
import random
import string
import urllib.request
import urllib.error
import re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)


def rand_email():
    return "g3fix_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))


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
        page.on("response", lambda r: info("[resp %d] %s" % (r.status, r.url)) if r.status >= 400 else None)
        page.add_init_script("localStorage.setItem('__peaDevHooks','1');")

        try:
            # ── 0. 注册 + 建画布 ──
            email = rand_email()
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
                            data=json.dumps({"title": "g3fix", "type": "personal"}).encode(),
                            headers={"Content-Type": "application/json",
                                     "Authorization": "Bearer %s" % tok},
                        ), timeout=15).read().decode())
                    canvas_id = cv.get("id")
                    canvas_ver = cv.get("version", 1)
                except Exception as ex:
                    info("create canvas failed: %s" % ex)
            info("user=%s canvas=%s" % (email, canvas_id))

            page.add_init_script("""
                localStorage.setItem('pea_token', ' """ + (tok or "x") + """ ');
                localStorage.setItem('pea_user', JSON.stringify({ id: 1, email: ' """ + email + """ ' }));
                localStorage.setItem('pea_ui_route', JSON.stringify({ active: 'canvas', canvasId: """ + str(canvas_id or 1) + """ }));
            """)

            page.route(re.compile(r".*?/users/me.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": 1, "email": email, "displayName": "Tester",
                                 "balance": 0, "isAdmin": False, "planLevel": 0,
                                 "effectivePlanLevel": 0, "planExpiresAt": None})))
            page.route(re.compile(r".*?/auth/refresh.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"token": tok or "x"})))
            page.route(re.compile(r".*?/canvases(\?.*)?$"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "data": []})))
            page.route(re.compile(r".*?/canvases/\d+.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": canvas_id or 1, "title": "g3fix", "version": canvas_ver,
                                 "graph_json": {"nodes": [], "edges": []}})))
            page.route(re.compile(r".*?/models/available.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps([
                    {"id": "agnes-2.1-flash", "providerId": "agnes", "type": "image",
                     "modelType": "image", "name": "Agnes 2.1 Flash", "displayName": "Agnes 2.1 Flash",
                     "unlocked": True, "basePrice": 1}
                ])))
            page.route(re.compile(r".*?/models/estimate.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"estimate": 1})))

            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            cur = page.evaluate("location.href")
            if "/login" in cur:
                page.evaluate("""() => { const ui = window.__ui && window.__ui.getState(); if (ui) ui.setActive('canvas'); }""")
                page.wait_for_timeout(1500)
            try:
                page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
            except Exception as ex:
                fail("dev hooks", "window.__canvas 未出现: %s" % ex)
                page.screenshot(path=os.path.join(SHOTS, "debug_g3_nohook.png"))
                return results
            page.wait_for_timeout(1200)
            ok("dev hooks (window.__canvas 暴露)")

            # ── 1. 注入 4 个文本节点 ──
            page.evaluate("""([cid, ver]) => {
                const cs = window.__canvas.getState();
                cs.setCanvasMeta(cid, ver, 'g3fix');
                cs.loadGraph([
                  { id: 't1', type: 'pea', position: { x: 200, y: 200 }, data: { kind: 'text', label: 'T1', html: '<p>T1</p>' } },
                  { id: 't2', type: 'pea', position: { x: 600, y: 200 }, data: { kind: 'text', label: 'T2', html: '<p>T2</p>' } },
                  { id: 't3', type: 'pea', position: { x: 200, y: 550 }, data: { kind: 'text', label: 'T3', html: '<p>T3</p>' } },
                  { id: 't4', type: 'pea', position: { x: 600, y: 550 }, data: { kind: 'text', label: 'T4', html: '<p>T4</p>' } },
                ], [], ver);
            }""", [canvas_id or 1, canvas_ver])
            page.wait_for_timeout(2000)
            page.wait_for_function("""() => {
                const ns = document.querySelectorAll('.react-flow__node[data-id]');
                return ns.length >= 4 && Array.from(ns).every(n => n.getBoundingClientRect().width > 0);
            }""", timeout=12000)
            ok("注入 4 节点")

            # ── 2. 打组并选中 ──
            gid = page.evaluate("() => window.__canvas.getState().groupNodes(['t1','t2','t3','t4'])")
            info("打组 gid=%s" % gid)
            page.wait_for_timeout(1500)
            page.evaluate("([g]) => window.__canvas.getState().setSelection([g])", [gid])
            page.wait_for_timeout(1200)
            page.screenshot(path=os.path.join(SHOTS, "verify_g3_grouped.png"))

            # ════════════════════════════════════
            # 修复1：组名在框左上角，工具条不显示组名/图标
            # ════════════════════════════════════
            label_state = page.evaluate("""() => {
                const labelEl = document.querySelector('.pea-group-node-label');
                const portal = document.querySelector('.pgn-header-portal');
                const left = portal ? portal.querySelector('.pgn-header-left') : null;
                const leftLabel = left ? left.textContent : '';
                const leftIcon = left ? left.querySelector('.anticon, svg') : null;
                return {
                    labelFound: !!labelEl,
                    labelText: labelEl ? labelEl.textContent.trim() : '',
                    portalFound: !!portal,
                    headerLeftFound: !!left,
                    headerLeftText: leftLabel.trim(),
                    hasHeaderIcon: !!leftIcon,
                };
            }""")
            info("组名状态: %s" % label_state)
            if label_state["labelFound"] and label_state["labelText"] == "新建组":
                ok("修复1a：组名显示为框左上角标签", "text=%s" % label_state["labelText"])
            else:
                fail("修复1a：组名标签", "found=%s text=%s" % (label_state["labelFound"], label_state["labelText"]))

            if not label_state["headerLeftFound"] or not label_state["hasHeaderIcon"]:
                ok("修复1b：工具条不再显示带图标的组名", "headerLeft=%s hasIcon=%s" % (label_state["headerLeftFound"], label_state["hasHeaderIcon"]))
            else:
                fail("修复1b：工具条仍含旧组名/图标", "text=%s" % label_state["headerLeftText"])

            # ════════════════════════════════════
            # 修复2：背景切换 UI 与功能
            # ════════════════════════════════════
            color_state = page.evaluate("""() => {
                const btn = document.querySelector('.pgn-color-btn');
                const portal = document.querySelector('.pgn-header-portal');
                const oldSvg = portal ? portal.querySelector('.pgn-color-icon') : null;
                const oldNameAsLabel = Array.from(portal ? portal.querySelectorAll('*') : []).some(
                    el => el.textContent && el.textContent.trim() === '新建组' && !el.classList.contains('pea-group-node-label')
                );
                return {
                    btnFound: !!btn,
                    btnText: btn ? btn.textContent.trim() : '',
                    hasOldPaintSvg: !!oldSvg,
                    nameMisplacedAsBg: oldNameAsLabel,
                };
            }""")
            info("颜色按钮状态: %s" % color_state)
            if color_state["btnFound"] and "切换背景" in color_state["btnText"]:
                ok("修复2a：按钮文案为\"切换背景\"", "text=%s" % color_state["btnText"])
            else:
                fail("修复2a：按钮文案", "found=%s text=%s" % (color_state["btnFound"], color_state["btnText"]))
            if not color_state["hasOldPaintSvg"]:
                ok("修复2b：旧油漆桶 svg 图标已移除", "")
            else:
                fail("修复2b：旧油漆桶 svg 仍存在", "")

            # 点击展开色板
            page.click('.pgn-color-btn')
            page.wait_for_timeout(400)
            panel_state = page.evaluate("""() => {
                const panel = document.querySelector('.pgn-color-panel');
                return {
                    panelFound: !!panel,
                    optionCount: panel ? panel.querySelectorAll('.pgn-color-option').length : 0,
                };
            }""")
            info("色板状态: %s" % panel_state)
            if panel_state["panelFound"] and panel_state["optionCount"] >= 2:
                ok("修复2c：点击展开圆点色板", "options=%d" % panel_state["optionCount"])
            else:
                fail("修复2c：色板未展开", "found=%s options=%d" % (panel_state["panelFound"], panel_state["optionCount"]))
            page.screenshot(path=os.path.join(SHOTS, "verify_g3_color_panel.png"))

            # 选择第二个非透明颜色
            page.evaluate("""() => {
                const opts = document.querySelectorAll('.pgn-color-option');
                if (opts.length > 1) opts[1].click();
            }""")
            page.wait_for_timeout(600)
            bg_after = page.evaluate("""() => {
                const g = document.querySelector('.pea-group-node');
                return g ? window.getComputedStyle(g).backgroundColor : null;
            }""")
            store_bg = page.evaluate("""() => {
                const s = window.__canvas.getState();
                const g = s.nodes.find(n => n.type === 'group');
                return g ? (g.data.bgColor || 'transparent') : null;
            }""")
            info("背景色: DOM=%s store=%s" % (bg_after, store_bg))
            if bg_after and bg_after != "rgba(0, 0, 0, 0)" and store_bg and store_bg != "transparent":
                ok("修复2d：选择颜色后组背景色改变", "bg=%s" % bg_after)
            else:
                fail("修复2d：背景色未改变", "DOM=%s store=%s" % (bg_after, store_bg))
            page.screenshot(path=os.path.join(SHOTS, "verify_g3_color_applied.png"))

            # ════════════════════════════════════
            # 修复3：解组后选择框消失
            # ════════════════════════════════════
            page.evaluate("([g]) => window.__canvas.getState().ungroupNode(g)", [gid])
            page.wait_for_timeout(1200)
            page.screenshot(path=os.path.join(SHOTS, "verify_g3_ungrouped.png"))

            ungroup_state = page.evaluate("""() => {
                return {
                    groupNodes: document.querySelectorAll('.pea-group-node').length,
                    selectionBounds: document.querySelectorAll('.pea-selection-bounds').length,
                    headerPortal: document.querySelectorAll('.pgn-header-portal').length,
                    selectedIds: window.__canvas.getState().selectedIds,
                    selectedId: window.__canvas.getState().selectedId,
                };
            }""")
            info("解组后状态: %s" % ungroup_state)
            if ungroup_state["groupNodes"] == 0:
                ok("修复3a：解组后组容器消失", "")
            else:
                fail("修复3a：解组后组容器仍存在", "count=%d" % ungroup_state["groupNodes"])
            if ungroup_state["selectionBounds"] == 0:
                ok("修复3b：解组后选择框消失", "")
            else:
                fail("修复3b：解组后选择框残留", "count=%d" % ungroup_state["selectionBounds"])
            if ungroup_state["headerPortal"] == 0:
                ok("修复3c：解组后工具条 portal 消失", "")
            else:
                fail("修复3c：解组后工具条 portal 残留", "count=%d" % ungroup_state["headerPortal"])
            if not ungroup_state["selectedIds"] and not ungroup_state["selectedId"]:
                ok("修复3d：解组后选中态清空", "selectedIds=%s" % ungroup_state["selectedIds"])
            else:
                fail("修复3d：解组后选中态未清空", "selectedIds=%s selectedId=%s" % (ungroup_state["selectedIds"], ungroup_state["selectedId"]))

        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append(("ERROR", str(e), ""))
            print(f"  [ERROR] {e}")
            try:
                page.screenshot(path=os.path.join(SHOTS, "debug_g3_error.png"))
            except Exception:
                pass
        finally:
            browser.close()

    print("\n" + "=" * 60)
    for r in results:
        print(f"  [{r[0]}] {r[1]}{(' — ' + r[2]) if len(r) > 2 and r[2] else ''}")
    p = sum(1 for r in results if r[0] == "PASS")
    f = sum(1 for r in results if r[0] == "FAIL")
    e = sum(1 for r in results if r[0] == "ERROR")
    print("=" * 60)
    print(f"总计 {len(results)} | PASS {p} | FAIL {f} | ERROR {e}")
    print("\n[console errors captured]")
    for ce in console_errors[-15:]:
        print("  -", ce[:180])
    return 0 if (f == 0 and e == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
