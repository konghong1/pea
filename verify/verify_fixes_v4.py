"""验证四项画布交互修复（真跑浏览器）：
1) 连接点仅悬停显示、鼠标小范围跟随、移出消失
2) 连线锚点在节点框垂直中间
3) 多选时选框透明 + 单节点无 .selected 功能框
4) 添加按钮在选中框右侧、节点卡样式、与节点框同距
复用登录/建节点/连线/框选流程。
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
        page.fill('input[placeholder="you@pea.ai"]', f"vf_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "VF")
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

        add_at("文本", 360, 320)
        add_at("图片", 1040, 320)
        page.wait_for_timeout(800)
        nodes = page.locator(".react-flow__node")
        n0 = nodes.nth(0); n1 = nodes.nth(1)

        # 连接 A -> B
        def connect(src_node, tgt_node):
            sbox = src_node.locator(".react-flow__handle.source").first.bounding_box()
            tbox = tgt_node.locator(".react-flow__handle.target").first.bounding_box()
            sx, sy = sbox["x"]+sbox["width"]/2, sbox["y"]+sbox["height"]/2
            tx, ty = tbox["x"]+tbox["width"]/2, tbox["y"]+tbox["height"]/2
            page.mouse.move(sx, sy); page.mouse.down()
            page.mouse.move((sx+tx)/2, (sy+ty)/2, steps=8)
            page.mouse.move(tx, ty, steps=8); page.mouse.up()
            page.wait_for_timeout(500)
        connect(n0, n1)

        # 点空白取消选择
        page.mouse.click(700, 650); page.wait_for_timeout(300)

        # ── 需求1: 连接点默认隐藏 ──
        src0 = n0.locator(".react-flow__handle.source").first
        op_hidden = src0.evaluate("el => getComputedStyle(el).opacity")
        out["handle_opacity_default"] = op_hidden
        checks.append(("连接点默认隐藏(opacity≈0)", float(op_hidden) < 0.1))

        # 框选 A、B
        page.mouse.move(180, 180); page.mouse.down()
        page.mouse.move(1240, 480, steps=12); page.mouse.up()
        page.wait_for_timeout(600)

        # ── 需求3: 选框透明 + 单节点无 .selected ──
        rect = page.locator(".react-flow__nodesselection-rect")
        rect_bg = rect.evaluate("el => getComputedStyle(el).backgroundColor") if rect.count() else "none"
        out["selection_rect_bg"] = rect_bg
        checks.append(("组选框透明(背景alpha=0)", rect_bg in ("rgba(0, 0, 0, 0)", "transparent")))
        # 注意：ReactFlow 给外层 .react-flow__node 始终加 selected（仅 z-index 用）；
        # 真正的「功能框」由内层 .pea-node.selected 驱动，多选时应被抑制。
        inner0 = n0.locator(".pea-node")
        node0_has_selected = "selected" in (inner0.get_attribute("class") or "")
        out["node0_has_selected_class"] = node0_has_selected
        checks.append(("多选单节点无.selected功能框类", not node0_has_selected))

        # 工具栏 + 加按钮出现
        toolbar = page.locator(".multiselect-toolbar")
        plus = page.locator(".multiselect-plus-btn")
        checks.append(("多选工具栏出现", toolbar.count() > 0))
        checks.append(("右侧添加按钮出现", plus.count() > 0))

        # ── 需求4: 添加按钮在右侧 + 节点卡样式 + 同距 ──
        plus_b = plus.bounding_box()
        n0b = n0.bounding_box(); n1b = n1.bounding_box()
        maxRight = max(n0b["x"]+n0b["width"], n1b["x"]+n1b["width"])
        centerY = ((n0b["y"]+n0b["height"]/2) + (n1b["y"]+n1b["height"]/2)) / 2
        plusCenterX = plus_b["x"] + plus_b["width"]/2
        plusCenterY = plus_b["y"] + plus_b["height"]/2
        gap = plus_b["x"] - maxRight   # 按钮近边 到 节点框 的距离
        out["plus_center_x"] = round(plusCenterX,1)
        out["plus_gap_from_box"] = round(gap,1)
        out["plus_center_y_vs_box_center"] = round(plusCenterY - centerY,1)
        out["plus_border_radius"] = plus.evaluate("el => getComputedStyle(el).borderRadius")
        checks.append(("添加按钮在选中框右侧", plusCenterX > maxRight))
        checks.append(("添加按钮距节点框≈同距(HANDLE_GAP=24)", 16 <= gap <= 34))
        checks.append(("添加按钮垂直居中于选区", abs(plusCenterY - centerY) < 30))
        br = out["plus_border_radius"]
        br_num = float(str(br).replace("px","").replace("%","")) if br not in ("50%",) else 999
        checks.append(("添加按钮为节点卡样式(非圆形)", 4 <= br_num <= 22))
        page.screenshot(path=str(SHOTS/"fix4_plus_right.png"))

        # ── 需求1: 悬停显示 + 跟随 + 锚点居中(需求2) ──
        page.mouse.move(700, 650); page.wait_for_timeout(300)
        hb0 = n0.bounding_box()
        page.mouse.move(hb0["x"]+hb0["width"]/2, hb0["y"]+hb0["height"]/2)
        page.wait_for_timeout(400)
        op_hover = src0.evaluate("el => getComputedStyle(el).opacity")
        out["handle_opacity_hover"] = op_hover
        checks.append(("悬停时连接点显示(opacity≈1)", float(op_hover) > 0.9))
        # 锚点垂直居中：handle 中心 Y 与节点中心 Y 差
        hb = src0.bounding_box()
        nb = n0.bounding_box()
        dy = abs((hb["y"]+hb["height"]/2) - (nb["y"]+nb["height"]/2))
        out["handle_vs_node_center_dy"] = round(dy,1)
        checks.append(("连线锚点在节点框垂直中间(dy<18)", dy < 18))
        # 跟随：移动鼠标到节点内不同位置，handle 横向偏移应变化
        r = n0.bounding_box()
        page.mouse.move(r["x"]+r["width"]*0.8, r["y"]+r["height"]*0.3)
        page.wait_for_timeout(200)
        hx_right = src0.evaluate("el => getComputedStyle(el).getPropertyValue('--pea-hx')")
        page.mouse.move(r["x"]+r["width"]*0.2, r["y"]+r["height"]*0.7)
        page.wait_after = None
        page.wait_for_timeout(200)
        hx_left = src0.evaluate("el => getComputedStyle(el).getPropertyValue('--pea-hx')")
        out["follow_hx_right"] = hx_right.strip()
        out["follow_hx_left"] = hx_left.strip()
        checks.append(("连接点随鼠标横向跟随(偏移变化)", hx_right.strip() != hx_left.strip()))
        page.screenshot(path=str(SHOTS/"fix1_hover.png"))

        # ── 需求1: 移出后消失 ──
        page.mouse.move(700, 650); page.wait_for_timeout(400)
        op_leave = src0.evaluate("el => getComputedStyle(el).opacity")
        out["handle_opacity_leave"] = op_leave
        checks.append(("鼠标移出后连接点消失(opacity≈0)", float(op_leave) < 0.1))

        out["page_errors"] = errors[:10]
        checks.append(("无运行时报错", len(errors) == 0))
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
