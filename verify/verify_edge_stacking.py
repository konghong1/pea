"""E2E 验证：连线默认压在节点下方；选中/高亮时单条边浮到节点上方。"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = "http://localhost:5173"
EMAIL = "test@example.com"
PASSWORD = "password123"
OUT = Path(__file__).resolve().parent / "verify"
OUT.mkdir(exist_ok=True)


def nav_to_canvas(page):
    if "/canvas" not in page.url:
        try:
            page.locator("text=未命名画布").first.click(timeout=6000)
        except Exception:
            page.locator("a[href*='/canvas']").first.click(timeout=6000)
    page.wait_for_selector(".react-flow__pane", timeout=30000)
    time.sleep(1)


def add_text_node(page, label, x, y):
    return page.evaluate(
        """([label, x, y]) => {
            const store = window.__canvas.getState();
            return store.addNode({
                kind: 'text',
                label: label,
                prompt: label,
                html: '<p>' + label + '</p>',
                meta: {},
            }, { x, y });
        }""",
        [label, x, y],
    )


def connect_nodes(page, source, target):
    return page.evaluate(
        """([source, target]) => {
            const api = window.__canvas;
            const id = 'e_' + source + '_' + target;
            api.setState({
                edges: [...api.getState().edges, {
                    id,
                    source,
                    target,
                    sourceHandle: null,
                    targetHandle: 'in',
                    type: 'pea',
                }],
                dirty: true,
            });
            return id;
        }""",
        [source, target],
    )


def get_edge_path_bounds(page, edge_id):
    return page.evaluate(
        """(edge_id) => {
            const path = document.querySelector(`[data-edge-id="${edge_id}"]`);
            if (!path) return null;
            const rect = path.getBoundingClientRect();
            return { x: rect.x, y: rect.y, w: rect.width, h: rect.height, cx: rect.x + rect.width/2, cy: rect.y + rect.height/2 };
        }""",
        edge_id,
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(f"{WEB}/login")
        page.fill("input#email, input[type='email']", EMAIL)
        page.fill("input#password, input[type='password']", PASSWORD)
        page.click("button:has-text('登 录')")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        if "/login" in page.url:
            raise RuntimeError("login failed")
        nav_to_canvas(page)

        # 清空画布，避免旧节点/旧边干扰本次测试
        page.evaluate("""() => {
            window.__canvas.getState().loadGraph([], [], 0);
        }""")
        time.sleep(0.5)

        # 添加两个文本节点：左 -> 右，但把目标节点移到连线中点附近，让线穿过节点
        n1 = add_text_node(page, "源", 250, 300)
        n2 = add_text_node(page, "目标", 650, 300)
        time.sleep(0.5)
        edge_id = connect_nodes(page, n1, n2)
        time.sleep(0.5)

        # 把目标节点移到连线中段，使连线穿过节点上方（视觉上看应被节点盖住）
        page.evaluate(
            """([n2id]) => {
                window.__canvas.getState().onNodesChange([{
                    id: n2id,
                    type: 'position',
                    position: { x: 430, y: 300 },
                    dragging: false,
                }]);
            }""",
            [n2],
        )
        time.sleep(0.8)

        page.screenshot(path=str(OUT / "edge_default_below.png"))

        # 断言：默认状态下，连线中点 elementsFromPoint 里节点应在边之前（边被压在下面）
        # 调试：打印节点和边的位置
        debug_pos = page.evaluate(
            """(edge_id) => {
                const allEdges = Array.from(document.querySelectorAll('.react-flow__edge'));
                const allNodes = Array.from(document.querySelectorAll('.react-flow__node'));
                const edge = allEdges.find((el) => {
                    const path = el.querySelector('.react-flow__edge-path');
                    return path?.getAttribute('data-edge-id') === edge_id;
                });
                const above = document.querySelector(`svg.pea-edge-above:has([data-edge-id="${edge_id}"])`)
                    || document.querySelector('.pea-edge-above');
                return {
                    nodeIds: allNodes.map((el) => el.getAttribute('data-id')),
                    edgeCount: allEdges.length,
                    edgeExists: !!edge,
                    edgeHTML: edge ? edge.outerHTML.slice(0, 400) : '',
                    aboveExists: !!above,
                    aboveHTML: above ? above.outerHTML.slice(0, 400) : '',
                    abovePathCount: above ? above.querySelectorAll('path').length : 0,
                    storeEdges: window.__canvas.getState().edges.map((e) => ({ id: e.id, s: e.source, t: e.target, sel: e.selected })),
                };
            }""",
            [edge_id],
        )
        print(f"positions: {debug_pos}")

        bounds = get_edge_path_bounds(page, edge_id)
        print(f"edge bounds: {bounds}")
        assert bounds, "未找到连线 path"

        def inspect_stack(cx, cy):
            return page.evaluate(
                """(pt) => {
                    const all = document.elementsFromPoint(pt.cx, pt.cy);
                    const items = all.slice(0, 12).map((el) => ({
                        tag: el.tagName,
                        cls: Array.from(el.classList).slice(0, 4).join('.'),
                        isNode: el.closest('.react-flow__node') != null,
                        isEdge: el.closest('.react-flow__edge') != null || el.classList.contains('pea-edge-above'),
                        isPath: el.classList.contains('react-flow__edge-path') || el.classList.contains('pea-edge-line'),
                    }));
                    const nodeIndex = items.findIndex((i) => i.isNode);
                    const edgeIndex = items.findIndex((i) => i.isEdge || i.isPath);
                    return { items, nodeIndex, edgeIndex };
                }""",
                {"cx": cx, "cy": cy},
            )

        stack_default = inspect_stack(bounds["cx"], bounds["cy"])
        print(f"[default] stack: {stack_default}")
        assert stack_default["nodeIndex"] != -1, "默认状态下应能命中节点"
        # 默认时边应不存在或位于节点之后
        assert stack_default["edgeIndex"] == -1 or stack_default["nodeIndex"] < stack_default["edgeIndex"], \
            "默认状态下连线应被压在节点下方"

        # 选中这条边：通过 store 同步选中状态
        page.evaluate(
            """(edge_id) => {
                const store = window.__canvas.getState();
                store.clearSelection();
                store.onEdgesChange([{ type: 'select', id: edge_id, selected: true }]);
                const e = store.edges.find((ed) => ed.id === edge_id);
                window.__edgeSelectedDebug = { edge_id, selected: e?.selected, edgesCount: store.edges.length };
            }""",
            edge_id,
        )
        time.sleep(0.5)
        print("debug:", page.evaluate("() => window.__edgeSelectedDebug"))
        page.screenshot(path=str(OUT / "edge_selected_above.png"))

        stack_selected = inspect_stack(bounds["cx"], bounds["cy"])
        print(f"[selected] stack: {stack_selected}")
        assert stack_selected["edgeIndex"] != -1, "选中后应存在边的视觉副本"
        assert stack_selected["edgeIndex"] < stack_selected["nodeIndex"], \
            "选中后边视觉副本应位于节点之上"

        # 取消选中，确认回到默认状态
        page.evaluate(
            """(edge_id) => {
                const store = window.__canvas.getState();
                store.onEdgesChange([{ type: 'select', id: edge_id, selected: false }]);
            }""",
            edge_id,
        )
        time.sleep(0.5)
        page.screenshot(path=str(OUT / "edge_deselected_below.png"))

        stack_deselected = inspect_stack(bounds["cx"], bounds["cy"])
        print(f"[deselected] stack: {stack_deselected}")
        assert stack_deselected["edgeIndex"] == -1 or stack_deselected["nodeIndex"] < stack_deselected["edgeIndex"], \
            "取消选中后连线应再次被压在节点下方"

        browser.close()
        print("PASS: edge stacking is correct (below by default, above when selected)")


if __name__ == "__main__":
    main()
