"""
诊断：文本节点"取消选中后再次单击"时输入框不弹出。
复现用户精确场景：创建节点 → 点空白取消 → 单击节点 → 看输入框是否出来 → 拖动后是否出来。
"""
from playwright.sync_api import sync_playwright
import time

SHOTS = "C:/workspace/pea/verify/shots"

def shot(page, name):
    page.screenshot(path=SHOTS + "/diag2_" + name + ".png", full_page=False)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errs = []
        page.on("console", lambda msg: errs.append(msg.text) if msg.type == "error" else None)
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)

        # 登录
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', "d2_%d@pea.dev" % ts)
        page.fill('input[placeholder*="至少"]', "Password123")
        page.fill('input[placeholder="可选"]', "D2")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        def add_node(label, x, y):
            page.mouse.dblclick(x, y)
            page.wait_for_timeout(350)
            page.locator(".pea-add-menu-item", has_text=label).first.click()
            page.wait_for_timeout(600)

        # 创建文本节点
        add_node("文本", 400, 280)
        print("[0] 文本节点已创建")
        shot(page, "00_created")

        def dom_state():
            return page.evaluate("""() => {
                var bar = document.querySelector('.node-chat-prompt');
                var toolbar = document.querySelector('.text-node-toolbar');
                var selectedNode = document.querySelector('.react-flow__node.selected');
                var allNodes = document.querySelectorAll('.react-flow__node');
                var nodeInfo = [];
                allNodes.forEach(function(n) {
                    // 尝试从 React fiber 读取实际的 data.kind
                    var reactKey = Object.keys(n).filter(function(k) { return k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'); })[0];
                    var fiberDataKind = null;
                    if (reactKey && n[reactKey]) {
                        try {
                            var fiber = n[reactKey];
                            while (fiber && !fiber.memoizedProps) fiber = fiber.return;
                            if (fiber && fiber.memoizedProps && fiber.memoizedProps.data) {
                                fiberDataKind = fiber.memoizedProps.data.kind;
                            }
                        } catch(e) {}
                    }
                    nodeInfo.push({
                        id: n.dataset.id,
                        domKind: n.dataset.kind,
                        sel: n.classList.contains('selected'),
                        fiberKind: fiberDataKind
                    });
                });
                return {
                    barExists: !!bar,
                    barDisplay: bar ? getComputedStyle(bar).display : null,
                    barDataKind: bar ? bar.getAttribute('data-kind') : null,
                    toolbarExists: !!toolbar,
                    toolbarDisplay: toolbar ? getComputedStyle(toolbar).display : null,
                    selectedNodeKind: selectedNode ? selectedNode.dataset.kind : null,
                    totalNodes: allNodes.length,
                    nodeInfo: nodeInfo
                };
            }""")

        st = dom_state()
        print("[INIT] bar=%s display=%s kind=%s toolbar=%s nodes=%s" % (
            st['barExists'], st['barDisplay'], st.get('barDataKind'), st['toolbarExists'],
            st['totalNodes']))
        for ni in st.get('nodeInfo', []):
            print("    node: id=%s domKind=%s fiberKind=%s sel=%s" % (ni['id'], ni.get('domKind'), ni.get('fiberKind'), ni['sel']))

        # ===== 场景A：点空白取消选中，再单击节点 =====
        print("\n[A] 点击空白取消选中...")
        page.mouse.click(80, 80)
        page.wait_for_timeout(500)
        st_a = dom_state()
        print("    取消后: bar=%s display=%s selected=%s" % (st_a['barExists'], st_a['barDisplay'], st_a['selectedNodeKind']))
        shot(page, "01_deselected")

        print("    -> 单击节点...")
        # 查找任意节点（不限制 kind）
        node_info = page.evaluate("""() => {
            var n = document.querySelector('.react-flow__node');
            if (!n) return null;
            var r = n.getBoundingClientRect();
            return { cx: r.left + r.width/2, cy: r.top + r.height/2, id: n.dataset.id, kind: n.dataset.kind };
        }""")
        if not node_info:
            print("    !! 无任何节点 !!")
            shot(page, "02_no_nodes")
            return
        print("    节点中心: (%.0f, %.0f) kind=%s id=%s" % (node_info['cx'], node_info['cy'], node_info['kind'], node_info['id']))

        page.mouse.click(node_info["cx"], node_info["cy"])
        page.wait_for_timeout(800)
        st_b = dom_state()
        print("    单击后:")
        print("      bar exists=%s display=%s kind=%s" % (st_b['barExists'], st_b['barDisplay'], st_b.get('barDataKind')))
        print("      toolbar exists=%s display=%s" % (st_b['toolbarExists'], st_b['toolbarDisplay']))
        print("      selected kind=%s" % st_b.get('selectedNodeKind'))
        if st_b.get('barRect'):
            r = st_b['barRect']
            print("      bar rect: x=%.0f y=%.0f w=%.0f h=%.0f" % (r['x'], r['y'], r['w'], r['h']))
        else:
            print("      bar rect: NULL !!!")
        shot(page, "02_after_reclick")

        # ===== 场景B：拖动节点 =====
        print("\n[B] 拖动节点 (+15, +5)...")
        page.mouse.move(node_info["cx"], node_info["cy"])
        page.mouse.down()
        page.mouse.move(node_info["cx"] + 15, node_info["cy"] + 5, steps=5)
        page.wait_for_timeout(150)
        page.mouse.up()
        page.wait_for_timeout(800)
        st_c = dom_state()
        print("    拖动后:")
        print("      bar exists=%s display=%s" % (st_c['barExists'], st_c['barDisplay']))
        print("      toolbar exists=%s display=%s" % (st_c['toolbarExists'], st_c['toolbarDisplay']))
        if st_c.get('barRect'):
            r = st_c['barRect']
            print("      bar rect: x=%.0f y=%.0f w=%.0f h=%.0f" % (r['x'], r['y'], r['w'], r['h']))
        shot(page, "03_after_drag")

        # ===== 场景C：Delete 删除连线 =====
        print("\n[C] Delete 键删除连线测试...")
        add_node("图片", 700, 280)
        page.wait_for_timeout(500)

        conn_result = page.evaluate("""() => {
            var srcHandle = document.querySelector('.react-flow__node[data-kind="text"] .react-flow__handle.source');
            var tgtNode = document.querySelector('.react-flow__node[data-kind="image"]');
            if (!srcHandle || !tgtNode) return { ok: false };
            var sr = srcHandle.getBoundingClientRect();
            var tr = tgtNode.getBoundingClientRect();
            return { ok: true, sx: sr.left+sr.width/2, sy: sr.top+sr.height/2, tx: tr.left+tr.width/2, ty: tr.top+tr.height/2 };
        }""")
        print("    连线参数: %s" % str(conn_result))

        if conn_result.get('ok'):
            page.mouse.move(conn_result['sx'], conn_result['sy'])
            page.mouse.down()
            page.mouse.move(conn_result['tx'], conn_result['ty'], steps=10)
            page.wait_for_timeout(200)
            page.mouse.up()
            page.wait_for_timeout(800)

            edge_count = page.evaluate("() => document.querySelectorAll('.react-flow__edge').length")
            print("    建边后 edge count: %d" % edge_count)

            if edge_count > 0:
                page.evaluate("""() => {
                    var path = document.querySelector('.react-flow__edge-path');
                    if (path) path.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                }""")
                page.wait_for_timeout(300)
                page.keyboard.press("Delete")
                page.wait_for_timeout(500)
                edge_count2 = page.evaluate("() => document.querySelectorAll('.react-flow__edge').length")
                print("    Delete 后 edge count: %d -> %s" % (edge_count2, 'PASS' if edge_count2 == 0 else 'FAIL'))
            shot(page, "04_edge_del_test")

        # 总结
        print("\n" + "=" * 60)
        bar_ok_a = st_b.get('barDisplay') not in ('none', None) and st_b.get('barExists')
        bar_ok_b = st_c.get('barDisplay') not in ('none', None) and st_c.get('barExists')
        print("结果:")
        print("  [A] 取消后再单击 -> bar=%s toolbar=%s" % ('PASS' if bar_ok_a else 'FAIL',
              'PASS' if st_b.get('toolbarDisplay') not in ('none', None) and st_b.get('toolbarExists') else 'FAIL'))
        print("  [B] 拖动后       -> bar=%s toolbar=%s" % ('PASS' if bar_ok_b else 'FAIL',
              'PASS' if st_c.get('toolbarDisplay') not in ('none', None) and st_c.get('toolbarExists') else 'FAIL'))

        console_errs = [e for e in errs if 'onNodesChange' not in e and 'react-dom' not in e]
        print("  Console errors: %d" % len(console_errs))
        for e in console_errs[:3]:
            print("    - %s" % e[:120])

if __name__ == "__main__":
    main()
