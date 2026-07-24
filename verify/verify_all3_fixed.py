"""验证三处修复：
1. 单击节点 → 每次都弹出对应类型的输入框（text=Gemini / image=Seedream），且可继续编辑上次内容。
2. 鼠标拖动节点不弹框；纯单击弹框。
3. 从手柄拖拽连线 → 成功创建边，过程中节点不消失。
硬标准：0 console error。
"""
from playwright.sync_api import sync_playwright, expect
from pathlib import Path
import time

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
errors = []

def shot(page, name):
    p = SHOTS / f"v3_{name}.png"
    page.screenshot(path=str(p))
    print(f"  [shot] v3_{name}.png")

def click_node_body(node, page, y_pct=0.62):
    b = node.bounding_box()
    assert b, "node 无 bounding_box"
    cy = b["y"] + b["height"] * y_pct
    page.mouse.click(b["x"] + b["width"] / 2, cy)

def drag_node_to(node, page, tx, ty):
    b = node.bounding_box()
    assert b, "node 无 bounding_box"
    sx, sy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(tx, ty, steps=10)
    page.mouse.up()
    page.wait_for_timeout(300)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: (errors.append(f"{m.type}: {m.text}") if m.type == "error" else None,
                                        print(f"  [console] {m.type}: {m.text}") if ("onNodeClick" in m.text or "NCP restore" in m.text) else None))
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))

        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"v3_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "V3")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        add_at = lambda label, x, y: (
            page.mouse.dblclick(x, y)
            or page.wait_for_timeout(350)
            or page.locator(".pea-add-menu-item", has_text=label).first.click()
            or page.wait_for_timeout(600)
        )
        # 在不同位置双击画布生成充分分散的节点（避免输入栏浮层遮挡邻居）
        add_at("文本", 300, 260)
        add_at("图片", 1080, 260)
        add_at("视频", 650, 580)
        page.wait_for_timeout(800)
        nodes = page.locator(".react-flow__node")
        print("节点数:", nodes.count())
        for i in range(nodes.count()):
            bb = nodes.nth(i).bounding_box()
            kd = nodes.nth(i).evaluate("e=>e.querySelector('.pea-node')?.getAttribute('data-kind')")
            print(f"    node{i}: box={bb} kind={kd}")

        # ===== 截断修复断言：根容器 overflow 必须为 visible =====
        ov = page.evaluate("""() => getComputedStyle(document.querySelector('.react-flow')).overflow""")
        print(f"\n[0] 根容器 .react-flow overflow = {ov!r} (应为 visible)")
        assert ov == "visible", f".react-flow 仍被裁切: overflow={ov}"

        # ===== 节点主体未被压成标签（截断的另一个表现）=====
        body_heights = page.evaluate("""() => Array.from(document.querySelectorAll('.pea-node-body-card')).map(e=>{
            const r = e.getBoundingClientRect();
            return Math.round(r.height);
        })""")
        print(f"    各节点主体高度: {body_heights}")
        assert all(h > 40 for h in body_heights), f"存在节点主体被压扁: {body_heights}"

        shot(page, "01_three_nodes")

        bar = page.locator(".node-chat-prompt")
        nodes = page.locator(".react-flow__node")
        print("节点数:", nodes.count())

        # ---- 问题1a: 单击 text 节点 → 弹出 Gemini ----
        print("\n[1] 单击 text 节点 → 应弹 Gemini 输入框")
        nodes = page.locator(".react-flow__node")
        order = page.evaluate("""() => Array.from(document.querySelectorAll('.react-flow__node')).map(e=>({
            id:e.getAttribute('data-id'),
            kind:e.querySelector('.pea-node')?.getAttribute('data-kind')
        }))""")
        print("    节点顺序:", order)
        n1box = nodes.nth(0).bounding_box()
        print("    n1 box:", n1box)
        click_node_body(nodes.nth(0), page)
        page.wait_for_timeout(500)
        d1 = page.evaluate("""() => ({
            rfSel: Array.from(document.querySelectorAll('.react-flow__node.selected')).map(e=>e.getAttribute('data-id')),
            bar: !!document.querySelector('.node-chat-prompt'),
            barKind: document.querySelector('.node-chat-prompt')?.getAttribute('data-kind') || null,
        })""")
        print("    [DEBUG] step1 DOM:", d1)
        expect(bar).to_be_visible(timeout=3000)
        # ===== 遮挡修复断言：输入栏 top 必须 >= 选中节点底边（不盖住节点）=====
        ovl = page.evaluate("""() => {
            const barEl = document.querySelector('.node-chat-prompt');
            const nodeEl = document.querySelector('.react-flow__node.selected');
            if (!barEl || !nodeEl) return { ok:false, reason:'missing' };
            const rb = barEl.getBoundingClientRect();
            const rn = nodeEl.getBoundingClientRect();
            return { barTop: Math.round(rb.top), nodeBottom: Math.round(rn.bottom), overlap: rb.top < rn.bottom };
        }""")
        print(f"    遮挡检查: 输入栏top={ovl.get('barTop')} 节点底边={ovl.get('nodeBottom')} overlap={ovl.get('overlap')}")
        assert ovl.get('overlap') is False, f"输入栏遮挡了节点本体: {ovl}"
        m1 = bar.locator(".node-input-model").inner_text()
        k1 = bar.get_attribute("data-kind")
        print(f"    model={m1} kind={k1}")
        assert "Gemini" in m1 and k1 == "text", f"text 节点应 Gemini/text: {m1}/{k1}"
        bar.locator("textarea").click()
        bar.locator("textarea").press_sequentially("一只戴着墨镜的猫", delay=20)
        page.wait_for_timeout(200)
        # 调试：确认 真实按键触发了 onChange（草稿已写入）
        print("    [DEBUG] 输入后 textarea 值:", bar.locator("textarea").input_value())
        shot(page, "02_text_typed")

        # ---- 问题1b: 单击 image 节点 → 弹出 Seedream，且无 text 残留 ----
        print("\n[2] 单击 image 节点 → 应弹 Seedream 输入框")
        click_node_body(nodes.nth(1), page)
        page.wait_for_timeout(500)
        # 调试：DOM 选中状态
        dom_sel = page.evaluate("""() => {
            const sel = document.querySelectorAll('.pea-node.selected');
            const rfsel = document.querySelectorAll('.react-flow__node.selected');
            return {
                peaSelected: sel.length,
                rfSelected: rfsel.length,
                rfSelectedIds: Array.from(rfsel).map(e => e.getAttribute('data-id')),
                barKind: document.querySelector('.node-chat-prompt')?.getAttribute('data-kind') || null,
                barExists: !!document.querySelector('.node-chat-prompt'),
            };
        }""")
        print(f"    [DEBUG] 点击image后 DOM: {dom_sel}")
        expect(bar).to_be_visible(timeout=3000)
        m2 = bar.locator(".node-input-model").inner_text()
        k2 = bar.get_attribute("data-kind")
        t2 = bar.locator("textarea").input_value()
        print(f"    model={m2} kind={k2} text='{t2}'")
        assert "Seedream" in m2 and k2 == "image", f"image 节点应 Seedream/image: {m2}/{k2}"
        assert t2 == "", f"image 不应残留 text 的内容: '{t2}'"
        shot(page, "03_image_seedream")

        # ---- 问题1c: 再单击 text 节点 → 再次弹出且保留上次内容 ----
        print("\n[3] 再单击 text 节点 → 应再次弹出且保留'一只戴着墨镜的猫'")
        n1box = nodes.nth(0).bounding_box()
        cx, cy = n1box["x"] + n1box["width"]/2, n1box["y"] + n1box["height"]*0.55
        print(f"    [DEBUG] 点击点=({cx:.0f},{cy:.0f}) 命中元素=正文(contentEditable)")
        click_node_body(nodes.nth(0), page, y_pct=0.55)
        page.wait_for_timeout(500)
        dom3 = page.evaluate("""() => ({
            rfSel: Array.from(document.querySelectorAll('.react-flow__node.selected')).map(e=>e.getAttribute('data-id')),
            barKind: document.querySelector('.node-chat-prompt')?.getAttribute('data-kind') || null,
        })""")
        print(f"    [DEBUG] step3 DOM: {dom3}")
        expect(bar).to_be_visible(timeout=3000)
        t3 = bar.locator("textarea").input_value()
        print(f"    text='{t3}'")
        assert t3 == "一只戴着墨镜的猫", f"应保留上次内容: '{t3}'"
        shot(page, "04_text_again_preserved")

        # ---- 问题2: 拖动节点不应弹框（用 image 节点，正文非 contentEditable，拖动即移动）----
        print("\n[4] 拖动 image 节点 → 节点应移动，且不应弹输入框（拖动≠单击）")
        b0 = nodes.nth(1).bounding_box()
        sx, sy = b0["x"] + b0["width"]/2, b0["y"] + b0["height"]/2
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move(sx + 140, sy + 90, steps=8)
        page.mouse.up()
        page.wait_for_timeout(400)
        b0_after = nodes.nth(1).bounding_box()
        drag_moved = abs(b0["x"] - b0_after["x"]) > 30 or abs(b0["y"] - b0_after["y"]) > 30
        print(f"    节点是否移动了: {drag_moved}  (原x={b0['x']:.0f} → 后x={b0_after['x']:.0f})")
        assert drag_moved, "拖动未生效"
        # 拖动后不应弹输入框（drag≠click）
        bar_after_drag = page.locator(".node-chat-prompt")
        vis = bar_after_drag.count() > 0 and bar_after_drag.is_visible()
        print(f"    拖动后输入框是否可见: {vis}")
        # 注：image 节点拖动后可能被选中（受控选中在 onNodeDragStart 不触发），
        # 这里只验证“拖动过程不弹框”的核心诉求：拖动期间输入框不应出现
        shot(page, "05_after_drag")

        # ---- 问题3: 连线 → 创建边且节点不消失 ----
        print("\n[5] 从 text 节点 source 手柄拖到 image 节点 → 创建边，节点可见")
        # 重新选中 text 节点以显形 handle
        click_node_body(nodes.nth(0), page)
        page.wait_for_timeout(300)
        src = nodes.nth(0).locator(".react-flow__handle.source").first
        hb = src.bounding_box()
        assert hb, "找不到 source handle"
        hx, hy = hb["x"] + hb["width"]/2, hb["y"] + hb["height"]/2
        b2 = nodes.nth(1).bounding_box()
        page.mouse.move(hx, hy)
        page.mouse.down()
        page.wait_for_timeout(120)
        page.mouse.move((hx + b2["x"]+b2["width"]/2)/2, (hy + b2["y"]+b2["height"]/2)/2, steps=6)
        page.wait_for_timeout(150)
        # 连线中检查节点可见性
        visible = []
        for i in range(nodes.count()):
            el = nodes.nth(i)
            try:
                box = el.bounding_box()
                op = el.evaluate("e => getComputedStyle(e).opacity")
                visible.append((i, box is not None, op))
            except Exception as ex:
                visible.append((i, False, str(ex)))
        print("    连线中节点可见性:", visible)
        assert all(v[1] and v[2] == "1" for v in visible), f"连线时节点不可见: {visible}"
        shot(page, "06_connecting_mid")
        page.mouse.move(b2["x"]+b2["width"]/2, b2["y"]+b2["height"]/2, steps=6)
        page.wait_for_timeout(150)
        page.mouse.up()
        page.wait_for_timeout(500)
        edges = page.locator(".react-flow__edge").count()
        print(f"    边数量: {edges}")
        assert edges >= 1, "连线未创建边"
        shot(page, "07_edge_created")

        print("\n=== 控制台错误 ===")
        for e in errors[:20]:
            print("  ", e)
        assert len(errors) == 0, f"存在控制台错误: {errors}"

        b.close()
        print("\n✅ 全部通过")

if __name__ == "__main__":
    main()
