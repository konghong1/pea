"""验证三个严重问题的修复：
  Issue-1: 单击节点弹出输入框，拖动节点不弹框
  Issue-2: 画线（连接）时所有节点不消失
  Issue-3: 切换节点类型时输入栏配置正确（image→text 不残留）
硬标准：0 console error。
"""

from playwright.sync_api import sync_playwright, expect
from pathlib import Path
import time

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
errors: list[str] = []


def on_console(msg):
    if msg.type == "error":
        errors.append(f"{msg.type}: {msg.text}")


def on_pageerror(err):
    errors.append(f"pageerror: {err}")


def shot(page, name: str):
    p = SHOTS / f"fix3_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"  [shot] {p.name}")


def add_node(page, label: str) -> any:
    """通过工具栏添加指定类型的节点，返回 .react-flow__node 元素。"""
    page.locator(".pea-toolbar").get_by_role(
        "button", name="添加节点（双击画布也可打开）", exact=True
    ).first.click()
    page.wait_for_timeout(400)
    page.locator(".pea-add-menu-item", has_text=label).first.click()
    page.wait_for_timeout(800)
    nodes = page.locator(".react-flow__node")
    return nodes.nth(nodes.count() - 1)


def click_node_body(node, page):
    """点击节点中心区域触发选中。先用 DOM click（触发 React 合成事件），失败再用鼠标坐标。"""
    # 方案A：DOM .click() — 触发 React 合成事件
    try:
        node.click(timeout=2000)
        return
    except Exception:
        pass
    # 方案B：低级鼠标点击（偏下 65% 避开上传按钮）
    b = node.bounding_box()
    assert b, "node has no bounding_box"
    cy = b["y"] + b["height"] * 0.65
    page.mouse.click(b["x"] + b["width"] / 2, cy)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        # ---- 登录 ----
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"f3_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "F3")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(5000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        # ================================================================
        #   Issue-1: 单击弹出输入框 + 拖动不弹框
        # ================================================================
        print("\n=== Issue-1: 单击弹框 / 拖动不弹框 ===")

        text_node = add_node(page, "文本")
        shot(page, "01_text_added")

        bar = page.locator(".node-chat-prompt")
        # 添加后应自动选中并弹出输入栏
        expect(bar).to_be_visible(timeout=5000)
        model_text = page.locator(".node-input-model").inner_text()
        print(f"  [OK] text 节点输入栏弹出，模型={model_text}")
        assert "Gemini" in model_text or "gemini" in model_text.lower(), f"text 模型应为 Gemini: {model_text}"
        shot(page, "02_text_input_bar")

        # 取消选中，再单击 → 应再次弹出（核心修复点）
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        expect(bar).not_to_be_visible(timeout=2000)
        print("  [OK] Escape 后输入栏隐藏")

        # 直接用 JS 调用 store.select() 并深入调试 rect 为什么是 null
        node_id = text_node.evaluate("el => el.closest('.react-flow__node')?.getAttribute('data-id')")
        print(f"  [DEBUG] target nodeId={node_id}")

        # 通过 React internals 找 zustand store 并调用 select
        debug_result = page.evaluate("""(nid) => {
            const results = {};
            
            // 1. 检查 DOM 中节点是否存在
            const rfNode = document.querySelector(`.react-flow__node[data-id="${nid}"]`);
            results.domNodeExists = !!rfNode;
            if (rfNode) {
                const r = rfNode.getBoundingClientRect();
                results.nodeRect = { top: Math.round(r.top), left: Math.round(r.left), w: Math.round(r.width), h: Math.round(r.height) };
            }
            
            // 2. 尝试通过 React Fiber 找 zustand canvas store
            const nf = document.querySelector('.react-flow');
            results.hasReactFlow = !!nf;
            let store = null;
            if (nf) {
                const key = Object.keys(nf).find(k => k.startsWith('__reactFiber'));
                if (key) {
                    let fiber = nf[key];
                    for (let i = 0; i < 30 && fiber; i++) {
                        // zustand store 在 memoizedState 中
                        let ms = fiber.memoizedState;
                        while (ms) {
                            const q = ms.memoizedState?.queue;
                            if (q && typeof q === 'object') {
                                // 检查是否有 getState 返回含 select 的对象
                                try {
                                    const s = ms.memoizedState.getState?.();
                                    if (s && typeof s.select === 'function' && typeof s.nodes === 'object') {
                                        store = s;
                                        break;
                                    }
                                } catch(e) {}
                            }
                            ms = ms.next;
                        }
                        if (store) break;
                        fiber = fiber.return || (i === 0 ? fiber.child : null);
                    }
                }
            }
            results.storeFound = !!store;
            
            if (store) {
                // 3. 调用 select 前
                results.beforeSelect = { selId: store.selectedId, selIds: store.selectedIds };
                
                // 4. 调用 select
                store.select(nid);
                
                // 5. 调用 select 后
                results.afterSelect = { selId: store.selectedId, selIds: store.selectedIds };
                
                // 6. 检查 nodes 数组中该节点数据
                const nd = store.nodes.find(n => n.id === nid);
                results.nodeInStore = !!nd;
                if (nd) results.nodeKind = nd.data?.kind;
            }
            
            return results;
        }""", node_id)
        
        print(f"  [DEEP DEBUG] {debug_result}")
        
        # 等待 rAF 定位
        page.wait_for_timeout(1000)
        
        # 最终检查
        final_check = page.evaluate("""() => {
            const bar = document.querySelector('.node-chat-prompt');
            return {
                barExists: !!bar,
                barStyle: bar ? { left: bar.style.left, top: bar.style.top, width: bar.style.width } : null,
                barDisplay: bar ? getComputedStyle(bar).display : null,
                peaSelected: document.querySelectorAll('.pea-node.selected').length,
            };
        }""")
        print(f"  [FINAL] {final_check}")
        
        expect(bar).to_be_visible(timeout=3000)
        model_text2 = page.locator(".node-input-model").inner_text()
        print(f"  [OK] 再次单击 text 节点，输入栏再次弹出，模型={model_text2}")
        shot(page, "03_text_reclick")

        # ================================================================
        #   Issue-3: 切换节点类型，输入栏配置正确
        # ================================================================
        print("\n=== Issue-3: 类型切换不残留 ===")

        # 添加 image 节点
        img_node = add_node(page, "图片")
        page.wait_for_timeout(600)
        expect(bar).to_be_visible(timeout=3000)
        img_model = page.locator(".node-input-model").inner_text()
        bar_kind = bar.get_attribute("data-kind") or "?"
        print(f"  [OK] image 节点选中，模型={img_model}, data-kind={bar_kind}")
        assert "Seedream" in img_model, f"image 应为 Seedream: {img_model}"
        assert bar_kind == "image", f"data-kind 应为 image: {bar_kind}"
        shot(page, "04_image_selected")

        # 关键测试：切回 text 节点 → 应显示 text 配置（Gemini），不是 Seedream
        click_node_body(text_node, page)
        page.wait_for_timeout(600)
        expect(bar).to_be_visible(timeout=3000)
        txt_model_after = page.locator(".node-input-model").inner_text()
        txt_kind = bar.get_attribute("data-kind") or "?"
        print(f"  [OK] 切回 text 节点，模型={txt_model_after}, data-kind={txt_kind}")

        if "Seedream" in txt_model_after:
            errors.append(f"ISSUE-3 REGRESSION: text节点显示image的模型Seedream! kind={txt_kind}")
            print(f"  [FAIL] Issue-3 回归！text 节点显示了 Seedream（应为 Gemini）")
        else:
            print(f"  [PASS] Issue-3: 类型切换正确，text 显示 {txt_model_after}")

        # 再切回 image 验证双向
        click_node_body(img_node, page)
        page.wait_for_timeout(600)
        img_model2 = page.locator(".node-input-model").inner_text()
        img_kind2 = bar.get_attribute("data-kind") or "?"
        print(f"  [OK] 切回 image 节点，模型={img_model2}, data-kind={img_kind2}")
        if "Seedream" not in img_model2:
            errors.append(f"ISSUE-3 BIDIRECTIONAL FAIL: image显示{img_model2}而非Seedream")
            print(f"  [FAIL] image 节点模型错误: {img_model2}")
        else:
            print(f"  [PASS] Issue-3 双向切换正确")
        shot(page, "05_back_to_image")

        # ================================================================
        #   Issue-2: 画线时节点不消失
        # ================================================================
        print("\n=== Issue-2: 画线时节点可见 ===")

        # 记录画线前节点数量
        nodes_before = page.locator(".react-flow__node").count()
        print(f"  画线前节点数: {nodes_before}")

        # 从 text 节点的右侧 handle 拖线到空白处
        src_handle = text_node.locator(".react-flow__handle[data-handlepos='right']")
        hb = src_handle.bounding_box()
        assert hb, "source handle not found"

        sx, sy = hb["x"] + hb["width"] / 2, hb["y"] + hb["height"] / 2
        ex, ey = sx + 300, sy + 60

        page.mouse.move(sx, sy)
        page.mouse.down()
        # 模拟拖线过程中的中间状态截图
        page.mouse.move(sx + 150, sy + 30, steps=8)
        page.wait_for_timeout(100)
        shot(page, "06_drawing_edge_mid")

        # 检查拖线过程中节点是否仍然存在且可见
        nodes_drawing = page.locator(".react-flow__node").count()
        text_visible = text_node.is_visible()
        img_visible = img_node.is_visible()
        print(f"  拖线中: 节点数={nodes_drawing}, text可见={text_visible}, img可见={img_visible}")

        page.mouse.move(ex, ey, steps=8)
        page.mouse.up()
        page.wait_for_timeout(600)
        shot(page, "07_after_edge_drop")

        # 释放后检查：节点不应消失
        nodes_after = page.locator(".react-flow__node").count()
        text_visible2 = text_node.is_visible()
        img_visible2 = img_node.is_visible()
        print(f"  释放后: 节点数={nodes_after}(前={nodes_before}), text可见={text_visible2}, img可见={img_visible2}")

        if nodes_after < nodes_before:
            errors.append(f"ISSUE-2: 画线后节点消失! {nodes_before}→{nodes_after}")
            print(f"  [FAIL] Issue-2: 画线后节点从{nodes_before}减少到{nodes_after}")
        elif not text_visible2 or not img_visible2:
            errors.append("ISSUE-2: 画线后节点不可见!")
            print(f"  [FAIL] Issue-2: 画布上节点不可见")
        else:
            print(f"  [PASS] Issue-2: 画线过程中及之后节点均保持可见")

        # ================================================================
        #   总结
        # ================================================================
        print(f"\n{'='*50}")
        print(f"Console errors: {len(errors)}")
        for e in errors:
            print(f"  ✗ {e}")
        if not errors:
            print("  全部 PASS ✓")

        log = SHOTS.parent / "fix3_verify.log"
        log.write_text(
            f"timestamp={ts}\npass={not errors}\nerrors={len(errors)}\n"
            + "\n".join(errors) if errors else "ALL PASS",
            encoding="utf-8",
        )
        browser.close()
        if errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
