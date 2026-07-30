"""端到端验证本次修复的三个画布交互问题：

问题1（连线）：连线应落在固定的连接点(in/out)上，而不是"吸"在节点框任意位置。
  - 从 source handle 拖到 target 节点"本体中心"（非手柄），断言：(a) 边数 +1；(b) 最新边的 targetHandle === 'in'。
问题2（框选可见 + 不触发下方节点）：框选时能透过选择框看到节点、且选择框不拦截事件、
  不弹出下方节点的弹框/输入栏。
  - 断言 .react-flow__selection 在拖拽中 pointer-events 为 none（不挡事件、可透视）+ 背景高度透明。
  - 断言被选中节点 opacity 仍 > 0（可见、未丢失）。
  - 断言框选期间 .node-chat-prompt 输入栏不出现（single===null 修复）。
  - 断言没有弹框/对话框出现。
问题3（框选后点功能不直接白屏、刷新能回初始态）：
  - 框选后点 MultiSelectToolbar 的"打组"功能（按钮文案为"打组"），断言无 pageerror、画布 viewport 仍在（非白屏）、并确实生成组节点。
  - 刷新页面后断言画布 viewport 仍可用（回到初始可操作态，不卡死白屏）。

复用 verify_multiselect.py 的登录/建节点流程。
"""
import sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "http://localhost:8088"
SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

checks = []
out = {}

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        # 开启 dev hooks，便于读取画布 store 断言 targetHandle
        page.add_init_script("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}")
        page.set_default_timeout(20000)
        errors = []
        logs = []
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
        def on_console(m):
            if m.type == "error":
                errors.append(f"{m.type}: {m.text}")
            if "[PEAEDGE]" in m.text:
                logs.append(m.text)
        page.on("console", on_console)

        # ── 登录 ──
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"t3_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "T3")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        try:
            page.get_by_role("button", name="新建项目").first.click()
            page.wait_for_timeout(3000)
            for _ in range(5):
                if page.locator(".react-flow__viewport").count() > 0:
                    break
                page.wait_for_timeout(1000)
        except Exception:
            pass
        page.wait_for_selector(".react-flow__viewport", timeout=20000)

        def add_at(label, x, y):
            page.mouse.dblclick(x, y)
            page.wait_for_timeout(350)
            page.locator(".pea-add-menu-item", has_text=label).first.click()
            page.wait_for_timeout(600)

        # 加两个节点：A 文本（左），B 图片（右）
        add_at("文本", 360, 320)
        add_at("图片", 1040, 320)
        page.wait_for_timeout(800)
        nodes = page.locator(".react-flow__node")
        n0 = nodes.nth(0)
        n1 = nodes.nth(1)
        out["node_count"] = nodes.count()

        # ── 问题1：从 A 的 source handle 拖到 B 的多个落点（右/中/左），均须固定到 'in' ──
        # 连接点现在随画布缩放且不再往节点框内跟进，必须真的点在 source handle 上发起连线。
        a_box = n0.bounding_box()
        page.mouse.move(a_box["x"] + a_box["width"] / 2, a_box["y"] + a_box["height"] / 2)
        page.wait_for_timeout(350)
        src_hb = page.evaluate("""() => {
            const n = document.querySelectorAll('.react-flow__node')[0];
            const h = n ? n.querySelector('.react-flow__handle.source') : null;
            if (!h) return null;
            const r = h.getBoundingClientRect();
            return {x: r.left + r.width/2, y: r.top + r.height/2, w: r.width, h: r.height};
        }""")
        out["src_hb_issue1a"] = src_hb
        sx = src_hb["x"] if src_hb else a_box["x"] + a_box["width"] - 5
        sy = src_hb["y"] if src_hb else a_box["y"] + a_box["height"] / 2
        t_box = n1.bounding_box()
        ty = t_box["y"] + t_box["height"] / 2
        # 分别落到 B 的右侧、中心、左侧；之前右侧会误吸到 source handle 'out'。
        drop_xs = [
            ("right", t_box["x"] + t_box["width"] - 8),
            ("center", t_box["x"] + t_box["width"] / 2),
            ("left", t_box["x"] + 8),
        ]
        edges_before = page.locator(".react-flow__edge").count()
        results = []
        for name, tx in drop_xs:
            # 每次循环都重新 hover 源节点并定位 source handle，避免鼠标离开节点后 handle 失活
            page.mouse.move(a_box["x"] + a_box["width"] / 2, a_box["y"] + a_box["height"] / 2)
            page.wait_for_timeout(250)
            src_hb = page.evaluate("""() => {
                const n = document.querySelectorAll('.react-flow__node')[0];
                const h = n ? n.querySelector('.react-flow__handle.source') : null;
                if (!h) return null;
                const r = h.getBoundingClientRect();
                return {x: r.left + r.width/2, y: r.top + r.height/2};
            }""")
            sx = src_hb["x"] if src_hb else a_box["x"] + a_box["width"] - 5
            sy = src_hb["y"] if src_hb else a_box["y"] + a_box["height"] / 2
            page.mouse.move(sx, sy)
            page.wait_for_timeout(100)
            page.mouse.down()
            page.mouse.move((sx + tx) / 2, (sy + ty) / 2, steps=8)
            page.mouse.move(tx, ty, steps=8)
            page.mouse.up()
            page.wait_for_timeout(500)
            edge_info = page.evaluate(
                """() => {
                    const st = window.__canvas && window.__canvas.getState();
                    if (!st) return null;
                    const es = st.edges || [];
                    return es.length ? {id: es[es.length-1].id, source: es[es.length-1].source, target: es[es.length-1].target, sourceHandle: es[es.length-1].sourceHandle, targetHandle: es[es.length-1].targetHandle} : null;
                }"""
            )
            results.append({"drop": name, "edge": edge_info})
            # 清掉这条边，避免 ReactFlow 因重复边而不触发 onConnect
            if edge_info and edge_info.get("id"):
                page.evaluate(f"""() => {{ const s = window.__canvas && window.__canvas.getState(); if (s) s.removeEdge('{edge_info['id']}'); }}""")
                page.wait_for_timeout(200)
        edges_after = page.locator(".react-flow__edge").count()
        out["edges_before"] = edges_before
        out["edges_after"] = edges_after
        out["drop_results"] = results
        created_count = sum(1 for r in results if r["edge"] is not None)
        all_on_in = all(r["edge"].get("targetHandle") == "in" for r in results if r["edge"])
        checks.append(("问题1a: 拖到节点本体不同位置均成功建边(3/3)", created_count == len(drop_xs)))
        checks.append(("问题1b: 所有入边均连到固定连接点(targetHandle='in')", all_on_in))

        # ── 问题1c：连线应连到「节点框」而非悬浮连接点 ──
        # 新建一条持久边（center 落点），检查边路径起点是否落在源节点框右缘。
        # 重新 hover A 并读取 source handle 位置（之前的拖拽可能改变了 hover 状态）。
        page.mouse.move(a_box["x"] + a_box["width"] / 2, a_box["y"] + a_box["height"] / 2)
        page.wait_for_timeout(350)
        src_hb = page.evaluate("""() => {
            const n = document.querySelectorAll('.react-flow__node')[0];
            const h = n ? n.querySelector('.react-flow__handle.source') : null;
            if (!h) return null;
            const r = h.getBoundingClientRect();
            return {x: r.left + r.width/2, y: r.top + r.height/2, w: r.width, h: r.height};
        }""")
        out["src_hb_issue1c"] = src_hb
        sx = src_hb["x"] if src_hb else a_box["x"] + a_box["width"] - 5
        sy = src_hb["y"] if src_hb else a_box["y"] + a_box["height"] / 2
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move((sx + (t_box["x"] + t_box["width"] / 2)) / 2, (sy + ty) / 2, steps=8)
        page.mouse.move(t_box["x"] + t_box["width"] / 2, ty, steps=8)
        page.mouse.up()
        page.wait_for_timeout(500)
        geom = page.evaluate(
            """() => {
                const path = document.querySelector('.react-flow__edge-path');
                if (!path) return null;
                const d = path.getAttribute('d') || '';
                const m = d.match(/^M\\s*([\\-0-9.]+)[ ,]([\\-0-9.]+)/);
                if (!m) return null;
                const pt = new DOMPoint(parseFloat(m[1]), parseFloat(m[2]));
                const ctm = path.getScreenCTM();
                const sp = ctm ? pt.matrixTransform(ctm) : null;
                const sn = document.querySelectorAll('.react-flow__node')[0];
                const srcBox = sn.getBoundingClientRect();
                const h = sn.querySelector('.react-flow__handle.source');
                const hb = h ? h.getBoundingClientRect() : null;
                return {
                    edgeStartX: sp ? sp.x : null,
                    srcRight: srcBox.right,
                    handleCx: hb ? (hb.x + hb.width / 2) : null,
                };
            }"""
        )
        out["geom"] = geom
        if geom and geom["edgeStartX"] is not None and geom["srcRight"] is not None:
            dx_box = geom["edgeStartX"] - geom["srcRight"]      # 期望≈0（连到框边）
            dx_handle = geom["edgeStartX"] - geom["handleCx"]  # 期望为负（边起点在 handle 中心左侧/框方向上）
            out["edge_start_dx_to_box"] = round(dx_box, 1)
            out["edge_start_dx_to_handle"] = round(dx_handle, 1) if dx_handle is not None else None
            on_box = abs(dx_box) <= 5 and (dx_handle is None or dx_handle < -6)
        else:
            on_box = False
        checks.append(("问题1c: 连线端点落在源节点框边(而非悬浮连接点)", on_box))
        page.screenshot(path=str(SHOTS / "t3_issue1_edge_on_box.png"))

        # ── 问题1d：放大/缩小后，连接点仍浮在框外固定间隔，连线仍连框边 ──
        def set_zoom(z: float):
            page.evaluate(f"""() => {{ if (window.__peaSetZoom) window.__peaSetZoom({z}); }}""")
            page.wait_for_timeout(500)

        def measure_at_zoom(z: float, label: str):
            set_zoom(z)
            d = page.evaluate(
                """() => {
                    const path = document.querySelector('.react-flow__edge-path');
                    const nodes = document.querySelectorAll('.react-flow__node');
                    const a = nodes[0], b = nodes[1];
                    if (!a || !b) return null;
                    const ab = a.getBoundingClientRect();
                    const bb = b.getBoundingClientRect();
                    const ah = a.querySelector('.react-flow__handle.source');
                    const bh = b.querySelector('.react-flow__handle.target');
                    const ahb = ah ? ah.getBoundingClientRect() : null;
                    const bhb = bh ? bh.getBoundingClientRect() : null;
                    let edgeStartX = null;
                    if (path) {
                        const dAttr = path.getAttribute('d') || '';
                        const m = dAttr.match(/^M\\s*([\\-0-9.]+)[ ,]([\\-0-9.]+)/);
                        if (m) {
                            const pt = new DOMPoint(parseFloat(m[1]), parseFloat(m[2]));
                            const ctm = path.getScreenCTM();
                            edgeStartX = ctm ? pt.matrixTransform(ctm).x : null;
                        }
                    }
                    return {
                        a_right: ab.right,
                        a_handle_cx: ahb ? ahb.x + ahb.width/2 : null,
                        b_left: bb.left,
                        b_handle_cx: bhb ? bhb.x + bhb.width/2 : null,
                        edgeStartX,
                    };
                }"""
            )
            page.screenshot(path=str(SHOTS / f"t3_issue1_zoom_{label}.png"))
            return d

        zoom_checks = []
        for z_label, z_val in [("2x", 2.0), ("0.5x", 0.5)]:
            zd = measure_at_zoom(z_val, z_label)
            out[f"zoom_{z_label}"] = zd
            if zd:
                # 连接点现在随画布缩放：handle 中心距框应为 HANDLE_GAP(=14) * zoom（视觉上缩放）
                z = 2.0 if z_label == "2x" else 0.5
                expected_gap = 14 * z
                gap_a = zd["a_handle_cx"] - zd["a_right"] if zd["a_handle_cx"] is not None else None
                gap_b = zd["b_left"] - zd["b_handle_cx"] if zd["b_handle_cx"] is not None else None
                edge_dx = zd["edgeStartX"] - zd["a_right"] if zd["edgeStartX"] is not None else None
                ok = (
                    gap_a is not None and abs(gap_a - expected_gap) <= 6
                    and gap_b is not None and abs(gap_b - expected_gap) <= 6
                    and edge_dx is not None and abs(edge_dx) <= 5
                )
                zoom_checks.append((f"问题1d[{z_label}]: 连接点浮框外且线连框边", ok,
                                    {"gap_a": gap_a, "gap_b": gap_b, "edge_dx": edge_dx, "expected_gap": expected_gap}))
            else:
                zoom_checks.append((f"问题1d[{z_label}]: 连接点浮框外且线连框边", False, None))
        for name, ok, detail in zoom_checks:
            checks.append((name, ok))
            out[f"zoom_check_{name}"] = detail

        # 后续框选测试基于 zoom=1 的屏幕坐标，重置缩放
        set_zoom(1.0)

        # 点空白取消选择
        page.mouse.click(720, 700)
        page.wait_for_timeout(300)

        # ── 问题2：框选 A、B（拖拽中检查选择框样式） ──
        page.mouse.move(180, 180)
        page.mouse.down()
        # 拖到半途，选择框此时可见
        page.mouse.move(700, 420, steps=10)
        page.wait_for_timeout(150)
        sel = page.locator(".react-flow__selection")
        sel_present = sel.count() > 0
        pe = sel.first.evaluate("el => getComputedStyle(el).pointerEvents") if sel_present else None
        bg = sel.first.evaluate("el => getComputedStyle(el).backgroundColor") if sel_present else None
        out["selection_present_during_drag"] = sel_present
        out["selection_pointer_events"] = pe
        out["selection_background"] = bg
        # 背景透明度：rgba(r,g,b,a) 的 a 应很小（透视）
        alpha = None
        if bg and bg.startswith("rgba"):
            try:
                alpha = float(bg.rsplit(",", 1)[1].rstrip(")"))
            except Exception:
                alpha = None
        out["selection_bg_alpha"] = alpha
        checks.append(("问题2a: 选择框拖拽中存在", sel_present))
        checks.append(("问题2b: 选择框 pointer-events=none(不挡事件/可透视)", pe == "none"))
        checks.append(("问题2c: 选择框背景高度透明(alpha<=0.1)", alpha is not None and alpha <= 0.1))

        # 完成框选
        page.mouse.move(1240, 480, steps=10)
        page.mouse.up()
        page.wait_for_timeout(600)

        # 2d) 被选中节点可见（opacity > 0，未丢失）
        vis = []
        for i in range(nodes.count()):
            op = nodes.nth(i).evaluate("el => parseFloat(getComputedStyle(el).opacity)")
            vis.append(op)
        out["node_opacities"] = vis
        checks.append(("问题2d: 选中节点均可见(opacity>0)", all(o > 0 for o in vis)))

        # 2e) 框选期间不应出现底部输入栏(.node-chat-prompt)—— single===null 修复
        ncp = page.locator(".node-chat-prompt").count()
        out["node_chat_prompt_count_during_boxselect"] = ncp
        checks.append(("问题2e: 框选期间无底部输入栏弹框", ncp == 0))

        # 2f) 不应有对话框/弹框出现
        dlg = page.locator("[role=dialog], .pea-modal, .ant-modal").count()
        out["dialog_count_during_boxselect"] = dlg
        checks.append(("问题2f: 框选期间无对话框弹出", dlg == 0))

        toolbar_visible = page.locator(".multiselect-toolbar").count() > 0
        out["multiselect_toolbar_visible"] = toolbar_visible
        checks.append(("多选工具栏出现", toolbar_visible))
        page.screenshot(path=str(SHOTS / "t3_issue2_boxselect.png"))

        # ── 问题3：框选后点"打组"功能（MultiSelectToolbar 实际按钮文案为"打组"），
        #    不应白屏；刷新应回初始态 ──
        pack = page.locator(".mst-btn:has-text('打组')")
        pack_clicked = False
        group_before = page.locator(".pea-group-node").count()
        if pack.count() > 0:
            try:
                pack.first.click()
                pack_clicked = True
                page.wait_for_timeout(1000)
            except Exception as ex:
                out["pack_error"] = str(ex)
        out["pack_clicked"] = pack_clicked
        group_after = page.locator(".pea-group-node").count()
        out["group_nodes_before"] = group_before
        out["group_nodes_after"] = group_after
        # 既点击成功，又确实生成了组节点（功能真的生效，而非假点）
        checks.append(("问题3a: 框选后可点击'打组'功能并成功建组", pack_clicked and group_after > group_before))

        # 关键：点击功能后画布 viewport 仍在（非白屏）
        viewport_after = page.locator(".react-flow__viewport").count()
        out["viewport_after_pack"] = viewport_after
        checks.append(("问题3b: 点击功能后画布未白屏(viewport仍在)", viewport_after > 0))

        # 关键：刷新后回到可用初始态（viewport 仍存在，不卡死白屏）
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        recovered = False
        for _ in range(8):
            if page.locator(".react-flow__viewport").count() > 0:
                recovered = True
                break
            ent = page.locator(".project-card, .pea-project-card").first
            if ent.count() > 0:
                try:
                    ent.click()
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
            page.wait_for_timeout(800)
        out["recovered_after_reload"] = recovered
        checks.append(("问题3c: 刷新后回到可用初始态(非白屏卡死)", recovered))
        out["page_errors"] = errors[:10]
        out["peaedge_logs"] = logs[:20]
        checks.append(("无运行时崩溃报错", len([e for e in errors if 'PAGEERROR' in e]) == 0))
        page.screenshot(path=str(SHOTS / "t3_issue3_after_reload.png"))

        b.close()

    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("\n=== 断言 ===")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("\nRESULT:", "ALL PASS" if ok else "HAS FAIL")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
