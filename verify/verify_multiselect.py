"""端到端验证多选工具条功能（真跑浏览器，非仅编译）。
链路：添加2节点 -> 连 A->B -> 框选A,B -> 工具栏出现 -> 点+ -> 选择器出现
      -> 连线预览含"-> 新节点" -> 选类型 -> 新节点插入且连线重连。
复用 verify_handle_upgrade.py 的登录/建节点流程。
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
import time, json

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

def main():
    out = {}
    checks = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        page = b.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)

        page.goto("http://localhost:8088", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"vm_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "VM")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        try:
            page.get_by_role("button", name="新建项目").first.click()
            page.wait_for_timeout(3000)
            for _ in range(3):
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

        # 1) 添加两个节点（A 文本左，B 图片右）
        add_at("文本", 360, 320)
        add_at("图片", 1040, 320)
        page.wait_for_timeout(800)
        nodes = page.locator(".react-flow__node")
        n0 = nodes.nth(0); n1 = nodes.nth(1)
        out["after_add_node_count"] = nodes.count()

        # 2) 连接 A -> B（拖拽 source handle 到 target handle）
        def connect(src_node, tgt_node):
            # 连接点现在仅悬停时显示：先把鼠标移到源节点中心触发 hover，手柄才可见可抓取
            sb = src_node.bounding_box()
            page.mouse.move(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] / 2)
            page.wait_for_timeout(350)
            sbox = src_node.locator(".react-flow__handle.source").first.bounding_box()
            tbox = tgt_node.locator(".react-flow__handle.target").first.bounding_box()
            if not sbox or not tbox:
                return False
            sx, sy = sbox["x"]+sbox["width"]/2, sbox["y"]+sbox["height"]/2
            tx, ty = tbox["x"]+tbox["width"]/2, tbox["y"]+tbox["height"]/2
            page.mouse.move(sx, sy)
            page.mouse.down()
            page.mouse.move((sx+tx)/2, (sy+ty)/2, steps=8)
            page.mouse.move(tx, ty, steps=8)
            page.mouse.up()
            page.wait_for_timeout(500)
            return True
        connected = connect(n0, n1)
        out["connected"] = connected
        out["edge_after_connect"] = page.locator(".react-flow__edge").count()

        # 3) 先点空白取消选择
        page.mouse.click(700, 650)
        page.wait_for_timeout(300)

        # 4) 框选 A、B
        page.mouse.move(180, 180)
        page.mouse.down()
        page.mouse.move(1240, 480, steps=12)
        page.mouse.up()
        page.wait_for_timeout(600)

        # 5) 验证工具栏 + 中心+按钮出现
        toolbar = page.locator(".multiselect-toolbar")
        plus = page.locator(".multiselect-plus-btn")
        toolbar_visible = toolbar.count() > 0
        plus_visible = plus.count() > 0
        out["toolbar_visible"] = toolbar_visible
        out["plus_visible"] = plus_visible
        out["selected_count_attr"] = toolbar.get_attribute("aria-selected-count") if toolbar_visible else None
        checks.append(("多选工具栏出现", toolbar_visible))
        checks.append(("中心+按钮出现", plus_visible))
        checks.append(("选中数量=2", out["selected_count_attr"] == "2"))
        page.screenshot(path=str(SHOTS/"ms1_toolbar.png"))

        # 6) 点击+按钮 -> 选择器弹出
        plus.first.click()
        page.wait_for_timeout(500)
        picker = page.locator(".msnp-picker")
        picker_visible = picker.count() > 0
        out["picker_visible"] = picker_visible
        checks.append(("节点选择器弹出", picker_visible))
        page.screenshot(path=str(SHOTS/"ms2_picker.png"))

        # 7) 验证连线预览（"选择的点的右节点连线都显示出来"）
        edge_items = page.locator(".msnp-edge-item")
        edge_item_count = edge_items.count()
        edge_item_text = edge_items.first.inner_text() if edge_item_count > 0 else ""
        out["edge_preview_count"] = edge_item_count
        out["edge_preview_text"] = edge_item_text
        checks.append(("连线预览显示有连线", edge_item_count > 0))
        checks.append(("预览含'-> 新节点'标记", "新节点" in edge_item_text))

        # 8) 选择"文本"类型插入
        page.locator(".msnp-item", has_text="文本").first.click()
        page.wait_for_timeout(800)
        page.wait_for_selector(".react-flow__node", timeout=8000)
        final_nodes = page.locator(".react-flow__node").count()
        final_edges = page.locator(".react-flow__edge").count()
        out["final_node_count"] = final_nodes
        out["final_edge_count"] = final_edges
        checks.append(("新节点已插入(节点=3)", final_nodes == 3))
        # 修复后：仅重连"有右连线的选中节点"。A->B 中 A 有出边 -> 重连为 A->X + X->B，
        # B 作为下游不再无脑回连，故边=2（无环边）。
        checks.append(("连线重连后边数=2(无环边)", final_edges == 2))
        page.screenshot(path=str(SHOTS/"ms3_after_insert.png"))

        out["page_errors"] = errors[:10]
        checks.append(("无运行时报错", len(errors) == 0))
        b.close()

    # 输出
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
