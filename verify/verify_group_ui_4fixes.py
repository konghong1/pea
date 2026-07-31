"""
E2E 验证：打组 UI 4 项修复（2026-07-31）
  1) 选择框变细（.pea-selection-bounds 边框 1px）
  2) 打组后严格包裹（group rect == 子节点并集，无 16px 缝隙，PAD=0）
  3) 节点功能条仅在选中后出现（hover 不触发）
  4) 组工具条重构：油漆桶图标 + 竖线分组（第一组=颜色+布局，中间=执行/模板/解组，最后=下载），旧 .pgn-dot 已移除

通过 window.__canvas 注入节点 + 真实打组 + DOM 测量。
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


def rand_email():
    return "uifix_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))


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
                            data=json.dumps({"title": "ui 4fix", "type": "personal"}).encode(),
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

            import re as _re
            page.route(_re.compile(r".*?/users/me.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": 1, "email": email, "displayName": "Tester",
                                 "balance": 0, "isAdmin": False, "planLevel": 0,
                                 "effectivePlanLevel": 0, "planExpiresAt": None})))
            page.route(_re.compile(r".*?/auth/refresh.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"token": tok or "x"})))
            page.route(_re.compile(r".*?/canvases(\?.*)?$"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "data": []})))
            page.route(_re.compile(r".*?/canvases/\d+.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": canvas_id or 1, "title": "ui 4fix", "version": canvas_ver,
                                 "graph_json": {"nodes": [], "edges": []}})))
            # 防 401 拦截器误登出：/models/available 在本环境返回 401，会触发 token 清除 + 跳 login。
            # 模型对象须含 displayName / modelType（NodeChatPrompt 渲染时调用 m.displayName.toLowerCase()）。
            page.route(_re.compile(r".*?/models/available.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps([
                    {"id": "agnes-2.1-flash", "providerId": "agnes", "type": "image",
                     "modelType": "image", "name": "Agnes 2.1 Flash", "displayName": "Agnes 2.1 Flash",
                     "unlocked": True, "basePrice": 1}
                ])))
            page.route(_re.compile(r".*?/models/estimate.*"), lambda r, req: r.fulfill(
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
                page.screenshot(path=os.path.join(SHOTS, "debug_4fix_nohook.png"))
                return results
            page.wait_for_timeout(1200)
            ok("dev hooks (window.__canvas 暴露)")

            # ── 1. 注入 4 节点 2x2 网格 ──
            pre = page.evaluate("""() => ({
                url: location.href,
                hasRf: !!document.querySelector('.react-flow'),
                rfNodes: document.querySelectorAll('.react-flow__node[data-id]').length,
                bodyCls: document.body.className,
                canvasState: window.__canvas ? window.__canvas.getState().canvasId : null,
            })""")
            info("注入前诊断: %s" % pre)

            page.evaluate("""([cid, ver]) => {
                const cs = window.__canvas.getState();
                cs.setCanvasMeta(cid, ver, 'ui 4fix');
                cs.loadGraph([
                  { id: 't1', type: 'pea', position: { x: 200, y: 200 }, data: { kind: 'text', label: 'T1', html: '<p>T1</p>' } },
                  { id: 't2', type: 'pea', position: { x: 600, y: 200 }, data: { kind: 'text', label: 'T2', html: '<p>T2</p>' } },
                  { id: 't3', type: 'pea', position: { x: 200, y: 550 }, data: { kind: 'text', label: 'T3', html: '<p>T3</p>' } },
                  { id: 't4', type: 'pea', position: { x: 600, y: 550 }, data: { kind: 'text', label: 'T4', html: '<p>T4</p>' } },
                  { id: 'm1', type: 'pea', position: { x: 1000, y: 320 }, data: { kind: 'image', label: 'M1', resultUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC' } }
                ], [], ver);
            }""", [canvas_id or 1, canvas_ver])
            page.wait_for_timeout(2000)

            # 耐心等 ReactFlow 挂载
            try:
                page.wait_for_function("() => !!document.querySelector('.react-flow')", timeout=12000)
            except Exception as ex:
                info("ReactFlow 未挂载: %s" % ex)

            # 二次诊断：若 DOM 节点不足，用 setState 强制重渲染
            diag = page.evaluate("""() => ({
                hasRf: !!document.querySelector('.react-flow'),
                rfNodes: document.querySelectorAll('.react-flow__node[data-id]').length,
            })""")
            info("注入后诊断: %s" % diag)
            if diag["rfNodes"] < 4:
                info("DOM 节点不足，强制 setState 重注入")
                page.evaluate("""([cid, ver]) => {
                    const cs = window.__canvas.getState();
                    cs.setCanvasMeta(cid, ver, 'ui 4fix');
                    window.__canvas.setState({
                        canvasId: cid, version: ver, title: 'ui 4fix',
                        nodes: [
                            { id: 't1', type: 'pea', position: { x: 200, y: 200 }, data: { kind: 'text', label: 'T1', html: '<p>T1</p>' } },
                            { id: 't2', type: 'pea', position: { x: 600, y: 200 }, data: { kind: 'text', label: 'T2', html: '<p>T2</p>' } },
                            { id: 't3', type: 'pea', position: { x: 200, y: 550 }, data: { kind: 'text', label: 'T3', html: '<p>T3</p>' } },
                            { id: 't4', type: 'pea', position: { x: 600, y: 550 }, data: { kind: 'text', label: 'T4', html: '<p>T4</p>' } },
                            { id: 'm1', type: 'pea', position: { x: 1000, y: 320 }, data: { kind: 'image', label: 'M1', resultUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC' } }
                        ],
                        edges: [], selectedId: null, selectedIds: [], dirty: false,
                    });
                }""", [canvas_id or 1, canvas_ver])
                page.wait_for_timeout(2000)

            try:
                page.wait_for_function("""() => {
                    const ns = document.querySelectorAll('.react-flow__node[data-id]');
                    return ns.length >= 4 && Array.from(ns).every(n => n.getBoundingClientRect().width > 0);
                }""", timeout=12000)
                ok("注入 4 节点 (2x2 网格)")
            except Exception as ex:
                fail("注入 4 节点", "DOM 节点渲染超时: %s" % ex)
                page.screenshot(path=os.path.join(SHOTS, "debug_4fix_inject.png"))
                return results

            # ════════════════════════════════════
            # 打组 + 选中组
            # ════════════════════════════════════
            gid = page.evaluate("() => window.__canvas.getState().groupNodes(['t1','t2','t3','t4'])")
            info("打组 gid=%s" % gid)
            page.wait_for_timeout(1500)
            page.evaluate("([g]) => window.__canvas.getState().setSelection([g])", [gid])
            page.wait_for_timeout(1200)

            # ── 修复1：选择框变细 ──
            sel = page.evaluate("""() => {
                const el = document.querySelector('.pea-selection-bounds');
                if (!el) return { found: false };
                const cs = getComputedStyle(el);
                return { found: true, bw: cs.borderTopWidth, bg: cs.backgroundColor };
            }""")
            if not sel.get("found"):
                fail("修复1a：选择框存在", "找不到 .pea-selection-bounds（组选中后应出现）")
            else:
                bw = float(sel["bw"].replace("px", "")) if sel["bw"].endswith("px") else 99
                info("选择框 borderTopWidth=%s" % sel["bw"])
                if bw <= 1.5:
                    ok("修复1a：选择框边框变细", "borderTopWidth=%s (期望≈1px)" % sel["bw"])
                else:
                    fail("修复1a：选择框边框", "borderTopWidth=%s，仍偏厚（期望≤1.5px）" % sel["bw"])
                    page.screenshot(path=os.path.join(SHOTS, "debug_4fix_selbox.png"))

            grp_border = page.evaluate("""() => {
                const el = document.querySelector('.pea-group-node');
                if (!el) return { found: false };
                return { found: true, bw: getComputedStyle(el).borderTopWidth };
            }""")
            if grp_border.get("found"):
                bwb = float(grp_border["bw"].replace("px", ""))
                if bwb <= 1.5:
                    ok("修复1b：组容器边框变细", "borderTopWidth=%s (期望≈1px)" % grp_border["bw"])
                else:
                    fail("修复1b：组容器边框", "=%s，期望≤1.5px" % grp_border["bw"])

            page.screenshot(path=os.path.join(SHOTS, "verify_4fix_1.png"))

            # ── 修复2：严格包裹（无缝隙） ──
            wrap = page.evaluate("""() => {
                const g = document.querySelector('.pea-group-node');
                if (!g) return { ok: false, reason: 'no group' };
                const gr = g.getBoundingClientRect();
                const ids = ['t1','t2','t3','t4'];
                let minL=1e9, minT=1e9, maxR=-1e9, maxB=-1e9;
                for (const id of ids) {
                    const el = document.querySelector('.react-flow__node[data-id="'+id+'"]');
                    if (!el) return { ok: false, reason: 'missing child '+id };
                    const r = el.getBoundingClientRect();
                    minL = Math.min(minL, r.left); minT = Math.min(minT, r.top);
                    maxR = Math.max(maxR, r.right); maxB = Math.max(maxB, r.bottom);
                }
                return { ok: true,
                    gL: Math.round(gr.left), gT: Math.round(gr.top), gR: Math.round(gr.right), gB: Math.round(gr.bottom),
                    cL: Math.round(minL), cT: Math.round(minT), cR: Math.round(maxR), cB: Math.round(maxB) };
            }""")
            if not wrap.get("ok"):
                fail("修复2：包裹测量", wrap.get("reason", "?"))
            else:
                gapL = wrap["gL"] - wrap["cL"]
                gapT = wrap["gT"] - wrap["cT"]
                gapR = wrap["cR"] - wrap["gR"]
                gapB = wrap["cB"] - wrap["gB"]
                info("包裹间隙 L=%d T=%d R=%d B=%d" % (gapL, gapT, gapR, gapB))
                if max(abs(gapL), abs(gapT), abs(gapR), abs(gapB)) <= 2:
                    ok("修复2：组严格包裹子节点（无缝隙）", "最大间隙=%dpx (PAD=0)" % max(abs(gapL), abs(gapT), abs(gapR), abs(gapB)))
                else:
                    fail("修复2：包裹间隙", "L=%d T=%d R=%d B=%d（期望均≤2px）" % (gapL, gapT, gapR, gapB))
                    page.screenshot(path=os.path.join(SHOTS, "debug_4fix_wrap.png"))

            page.screenshot(path=os.path.join(SHOTS, "verify_4fix_2.png"))

            # ── 修复4：组工具条重构 ──
            hdr = page.evaluate("""() => {
                const portal = document.querySelector('.pgn-header-portal');
                if (!portal) return { found: false };
                const cs = getComputedStyle(portal);
                const colorBtns = portal.querySelectorAll('.pgn-color-btn');
                const seps = portal.querySelectorAll('.pgn-actions-sep');
                const layoutTrig = portal.querySelectorAll('.pgn-layout-trigger');
                const dot = portal.querySelector('.pgn-dot');
                const colorSvg = portal.querySelector('.pgn-color-btn svg');
                // DOM 顺序：第一个 sep 之前应有 color-btn + layout；第二个 sep 之后应有下载
                const all = Array.from(portal.querySelectorAll('.pgn-btn, .pgn-actions-sep'));
                const idxColor = all.findIndex(e => e.classList.contains('pgn-color-btn'));
                const idxLayout = all.findIndex(e => e.classList.contains('pgn-layout-trigger'));
                const idxSep1 = all.findIndex(e => e.classList.contains('pgn-actions-sep'));
                const idxSep2 = all.findIndex((e, i) => e.classList.contains('pgn-actions-sep') && i > idxSep1);
                const idxDownload = all.findIndex(e => e.title && e.title.indexOf('下载') >= 0);
                return {
                    found: true,
                    pos: cs.position, top: Math.round(portal.getBoundingClientRect().top),
                    nColor: colorBtns.length, nSep: seps.length, nLayout: layoutTrig.length,
                    hasDot: !!dot, hasColorSvg: !!colorSvg,
                    idxColor, idxLayout, idxSep1, idxSep2, idxDownload,
                };
            }""")
            if not hdr.get("found"):
                fail("修复4a：组工具条 portal", "找不到 .pgn-header-portal")
            else:
                if hdr["pos"] == "fixed":
                    ok("修复4a：组工具条定位 fixed (浮于框外顶部)", "top=%d" % hdr["top"])
                else:
                    fail("修复4a：组工具条定位", "position=%s，应为 fixed" % hdr["pos"])
                if hdr["nColor"] == 1 and hdr["hasColorSvg"]:
                    ok("修复4b：油漆桶颜色按钮存在(含svg图标)", "nColor=%d" % hdr["nColor"])
                else:
                    fail("修复4b：油漆桶颜色按钮", "nColor=%d hasSvg=%s（期望 1+svg）" % (hdr["nColor"], hdr["hasColorSvg"]))
                if hdr["hasDot"]:
                    fail("修复4c：旧 .pgn-dot 仍存在", "应已移除")
                else:
                    ok("修复4c：旧圆点 .pgn-dot 已移除", "")
                if hdr["nSep"] == 2:
                    ok("修复4d：竖线分隔符=2（3 组）", "")
                else:
                    fail("修复4d：分隔符数量", "=%d，期望 2" % hdr["nSep"])
                # 第一组：颜色 + 布局 在第一个 sep 之前
                first_group_ok = (hdr["idxColor"] >= 0 and hdr["idxLayout"] >= 0
                                  and hdr["idxColor"] < hdr["idxSep1"] and hdr["idxLayout"] < hdr["idxSep1"])
                if first_group_ok:
                    ok("修复4e：第一组=油漆桶+布局切换(位于首条竖线前)", "")
                else:
                    fail("修复4e：第一组顺序", "idxColor=%d idxLayout=%d idxSep1=%d" % (hdr["idxColor"], hdr["idxLayout"], hdr["idxSep1"]))
                # 下载在最后（第二条竖线之后）
                if hdr["idxDownload"] > hdr["idxSep2"] and hdr["idxSep2"] > hdr["idxSep1"]:
                    ok("修复4f：下载位于最后(第二条竖线后)", "")
                else:
                    fail("修复4f：下载位置", "idxDownload=%d idxSep2=%d idxSep1=%d" % (hdr["idxDownload"], hdr["idxSep2"], hdr["idxSep1"]))

            page.screenshot(path=os.path.join(SHOTS, "verify_4fix_4.png"))

            # ════════════════════════════════════
            # 修复3：节点功能条仅选中后出现（hover 不触发）
            # 用未打组的图片节点 m1 测试（图片节点才渲染 .pea-node-result-toolbar）
            # ════════════════════════════════════
            def m1_toolbar_state():
                return page.evaluate("""() => {
                    const node = document.querySelector('.react-flow__node[data-id="m1"]');
                    const docCount = document.querySelectorAll('.pea-node-result-toolbar').length;
                    if (!node) return { found: false, docCount };
                    const tb = node.querySelector('.pea-node-result-toolbar');
                    if (!tb) return { found: false, hasNode: true, docCount };
                    const cs = getComputedStyle(tb);
                    return { found: true, opacity: cs.opacity, pe: cs.pointerEvents, vis: cs.visibility, docCount };
                }""")

            page.evaluate("() => window.__canvas.getState().setSelection([])")
            page.wait_for_timeout(400)
            rect = page.evaluate("""() => {
                const el = document.querySelector('.react-flow__node[data-id="m1"]');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { cx: Math.round(r.left + r.width/2), cy: Math.round(r.top + r.height*0.7) };
            }""")
            if not rect:
                fail("修复3：m1 节点", "找不到 m1 DOM 元素")
            else:
                # 3a. hover 节点本体（不点击）
                page.mouse.move(rect["cx"], rect["cy"])
                page.wait_for_timeout(500)
                st_hover = m1_toolbar_state()
                info("hover 后工具栏: %s" % st_hover)
                if not st_hover.get("found"):
                    fail("修复3a：功能条元素", "m1 无 .pea-node-result-toolbar (docCount=%s)" % st_hover.get("docCount"))
                else:
                    hidden_on_hover = (float(st_hover["opacity"]) < 0.5) or (st_hover["pe"] == "none") or (st_hover["vis"] == "hidden")
                    if hidden_on_hover:
                        ok("修复3a：hover 节点功能条不出现", "opacity=%s pe=%s" % (st_hover["opacity"], st_hover["pe"]))
                    else:
                        fail("修复3a：hover 仍触发功能条", "opacity=%s pe=%s（应为隐藏）" % (st_hover["opacity"], st_hover["pe"]))
                        page.screenshot(path=os.path.join(SHOTS, "debug_4fix_hover.png"))

                # 3b. 点击选中 m1 → 功能条出现
                page.mouse.click(rect["cx"], rect["cy"])
                page.wait_for_timeout(600)
                st_sel = m1_toolbar_state()
                info("select 后工具栏: %s" % st_sel)
                if not st_sel.get("found"):
                    fail("修复3b：功能条元素", "m1 无 .pea-node-result-toolbar")
                else:
                    visible_on_select = (float(st_sel["opacity"]) >= 0.5) and (st_sel["pe"] != "none")
                    if visible_on_select:
                        ok("修复3b：选中后功能条出现", "opacity=%s pe=%s" % (st_sel["opacity"], st_sel["pe"]))
                    else:
                        fail("修复3b：选中功能条未出现", "opacity=%s pe=%s" % (st_sel["opacity"], st_sel["pe"]))
                        page.screenshot(path=os.path.join(SHOTS, "debug_4fix_select.png"))

            page.screenshot(path=os.path.join(SHOTS, "verify_4fix_3.png"))

        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append(("ERROR", str(e), ""))
            print(f"  [ERROR] {e}")
            try: page.screenshot(path=os.path.join(SHOTS, "debug_4fix_error.png"))
            except Exception: pass
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
