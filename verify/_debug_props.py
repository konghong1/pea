"""Debug: 检查节点 dragHandle 属性"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("C:/workspace/pea/verify/shots")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto("http://localhost:8088", wait_until="networkidle")
    page.wait_for_timeout(800)
    ts = int(time.time() * 1000)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', f"dbg3_{ts}@pea.ai")
    page.fill('input[placeholder="至少 8 位"]', "Password123")
    page.fill('input[placeholder="可选"]', "Dbg3")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(5000)
    page.wait_for_selector(".react-flow__viewport", timeout=15000)
    page.wait_for_timeout(1000)

    # 加一个 text 节点
    page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
    page.wait_for_selector(".pea-add-menu", timeout=4000)
    for it in page.locator(".pea-add-menu-item").all():
        if "文本" in (it.text_content() or ""):
            box = it.bounding_box()
            page.mouse.click(box["x"]+box["width"]/2, box["y"]+box["height"]/2)
            page.wait_for_timeout(600)
            break
    page.mouse.move(10, 10)
    page.wait_for_timeout(500)

    # 检查节点的 React props（通过 internal fiber）
    info = page.evaluate("""() => {
        // 找 zustand store 暴露的 canvas state
        const win = window;
        const keys = Object.keys(win).filter(k => k.toLowerCase().includes('store') || k.toLowerCase().includes('canvas'));
        return keys;
    }""")
    print(f"window keys with store/canvas: {info}")

    # 找 ReactFlow internal store
    info2 = page.evaluate("""() => {
        const dom = document.querySelector('.react-flow');
        if (!dom) return 'no react-flow dom';
        // React 18 内部 fiber
        const fiberKey = Object.keys(dom).find(k => k.startsWith('__reactFiber'));
        return { dom: !!dom, fiberKey };
    }""")
    print(f"react-flow dom: {info2}")

    # 直接 inspect 节点 data-id 属性 & node 字段
    info3 = page.evaluate("""() => {
        const nodes = Array.from(document.querySelectorAll('.react-flow__node'));
        return nodes.map(n => ({
            id: n.getAttribute('data-id'),
            className: n.className,
            // ReactFlow 节点上挂的 props via __reactProps
            reactPropsKeys: n[Object.keys(n).find(k => k.startsWith('__reactProps'))] ? Object.keys(n[Object.keys(n).find(k => k.startsWith('__reactProps'))]) : [],
        }));
    }""")
    print("NODES:", info3)

    # 关键：在 node element 上检查 ReactFlow 拖拽逻辑
    # ReactFlow 11 把 dragHandle 传给 NodeWrapper，NodeWrapper 调用 useDrag。
    # 我们直接看 useDrag 返回的 drag handler 是否正确
    info4 = page.evaluate("""() => {
        // 找 zustand 内部 store 通过 React Flow provider context
        // ReactFlow 把 store 挂到 domNode 的某个属性上
        const flow = document.querySelector('.react-flow');
        // 看 .react-flow__viewport 的 transform
        const vp = document.querySelector('.react-flow__viewport');
        return {
            flowTag: flow?.tagName,
            viewportTransform: vp?.style.transform,
        };
    }""")
    print(f"flow info: {info4}")

    # 测试点 handle 区域，看 ReactFlow 是否触发 handle 拖拽
    handles = page.locator('.react-flow__handle').all()
    if len(handles) >= 2:
        h = handles[0]
        box = h.bounding_box()
        cx = box['x'] + box['width']/2
        cy = box['y'] + box['height']/2
        print(f"handle 0 (left?) center: ({cx:.1f}, {cy:.1f})")

        # 直接 mousedown 看是否有 dragging 类
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.wait_for_timeout(200)
        is_dragging = page.evaluate("() => document.querySelector('.react-flow__node').className.includes('dragging')")
        print(f"after mousedown on handle 0: is_dragging = {is_dragging}")
        page.mouse.up()
        page.wait_for_timeout(300)

        h = handles[1]  # right handle
        box = h.bounding_box()
        cx = box['x'] + box['width']/2
        cy = box['y'] + box['height']/2
        print(f"handle 1 (right?) center: ({cx:.1f}, {cy:.1f})")
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.wait_for_timeout(200)
        is_dragging = page.evaluate("() => document.querySelector('.react-flow__node').className.includes('dragging')")
        print(f"after mousedown on handle 1: is_dragging = {is_dragging}")
        # 现在尝试拖到第二个 handle (如果存在)
        page.mouse.up()
        page.wait_for_timeout(300)

    # 加第二个节点
    page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
    page.wait_for_selector(".pea-add-menu", timeout=4000)
    for it in page.locator(".pea-add-menu-item").all():
        if "图片" in (it.text_content() or ""):
            box = it.bounding_box()
            page.mouse.click(box["x"]+box["width"]/2, box["y"]+box["height"]/2)
            page.wait_for_timeout(600)
            break
    page.mouse.move(10, 10)
    page.wait_for_timeout(500)

    # 现在尝试拖动 n1 的 right handle 到 n2 的 left handle
    handles = page.locator('.react-flow__handle').all()
    print(f"\n2 nodes -> {len(handles)} handles")
    nodes = page.locator('.react-flow__node').all()
    print(f"nodes count: {len(nodes)}")

    # n1 的 right handle
    src = nodes[0].locator('.react-flow__handle[data-handlepos="right"]').first
    src_box = src.bounding_box()
    sx = src_box["x"] + src_box["width"]/2
    sy = src_box["y"] + src_box["height"]/2
    # n2 的 left handle
    tgt = nodes[1].locator('.react-flow__handle[data-handlepos="left"]').first
    tgt_box = tgt.bounding_box()
    tx = tgt_box["x"] + tgt_box["width"]/2
    ty = tgt_box["y"] + tgt_box["height"]/2
    print(f"src ({nodes[0].get_attribute('data-id')}) right handle: ({sx:.1f}, {sy:.1f})")
    print(f"tgt ({nodes[1].get_attribute('data-id')}) left handle:  ({tx:.1f}, {ty:.1f})")

    page.mouse.move(sx, sy)
    page.mouse.down()
    page.wait_for_timeout(200)
    is_dragging = page.evaluate("() => Array.from(document.querySelectorAll('.react-flow__node')).some(n => n.className.includes('dragging'))")
    print(f"after mousedown on n1.right: any dragging = {is_dragging}")
    # 慢速移动
    steps = 30
    for i in range(1, steps+1):
        ix = sx + (tx - sx) * i / steps
        iy = sy + (ty - sy) * i / steps
        page.mouse.move(ix, iy)
        page.wait_for_timeout(30)
    page.wait_for_timeout(200)
    is_dragging = page.evaluate("() => Array.from(document.querySelectorAll('.react-flow__node')).some(n => n.className.includes('dragging'))")
    print(f"after move: any dragging = {is_dragging}")
    # 看 connection line
    conn = page.evaluate("() => document.querySelector('.react-flow__connection')")
    print(f"connection path: {'YES' if conn else 'NO'}")
    page.mouse.up()
    page.wait_for_timeout(500)
    edge_cnt = page.locator(".react-flow__edge").count()
    print(f"final edge count = {edge_cnt}")

    browser.close()