"""真机测试：缩放控件 + 节点连线。
目标：
  T1. 默认 ReactFlow Controls 已彻底移除（.react-flow__controls 元素不存在）
  T2. 自定义 ZoomControls 已渲染（.pea-zoom-controls 存在）
  T3. 节点 handle 默认显示小圆点（用户能看见拖线入口）
  T4. 拖动 source handle -> target handle 能创建边（边数从 0 变 1）
  T5. 点击放大按钮能改变 zoom 值
  T6. 0 console error
"""
import sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("C:/workspace/pea/verify/shots")
OUT.mkdir(parents=True, exist_ok=True)

def shot(page, name):
    p = OUT / f"zc_{name}.png"
    page.screenshot(path=str(p))
    print(f"  [shot] {p.name}")

def add_node(page, kind):
    """通过工具栏触发菜单，真实点击对应条目加节点"""
    btn = page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first
    btn.click(force=True)
    page.wait_for_selector(".pea-add-menu", timeout=4000)
    items = page.locator(".pea-add-menu-item").all()
    label_map = {"text": "文本", "image": "图片", "video": "视频", "audio": "音频"}
    for it in items:
        if label_map[kind] in (it.text_content() or ""):
            box = it.bounding_box()
            page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            page.wait_for_timeout(500)
            # 菜单关 + 鼠标移到角落避免 hover 节点
            page.mouse.move(10, 10)
            page.wait_for_timeout(300)
            return
    raise RuntimeError(f"menu item {kind} not found")

def main():
    fails = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        console_errors = []
        page.on("console", lambda m: m.type in ("error",) and console_errors.append((m.type, m.text)))
        page.on("pageerror", lambda e: console_errors.append(("pageerror", str(e))))

        # 1) 注册登录
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(800)
        ts = int(time.time() * 1000)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', f"zc_{ts}@pea.ai")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "ZCTEST")  # displayName (后端 register 必填)
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(5000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        # T1: 默认 Controls 已移除
        cnt = page.locator(".react-flow__controls").count()
        print(f"\n[T1] .react-flow__controls count = {cnt}")
        if cnt > 0:
            fails.append("T1: ReactFlow 默认 Controls 仍在")
        else:
            print("  ✅ PASS")

        # T2: 自定义 ZoomControls 已渲染
        cnt = page.locator(".pea-zoom-controls").count()
        print(f"\n[T2] .pea-zoom-controls count = {cnt}")
        if cnt == 0:
            fails.append("T2: 自定义 ZoomControls 未渲染")
        else:
            print("  ✅ PASS")
        shot(page, "01_canvas_with_zoom_controls")

        # T3: handle 默认显示小圆点（先点空白取消选中）
        add_node(page, "text")
        page.wait_for_timeout(400)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        # 验证 handle 可见
        handles = page.locator(".react-flow__handle.pea-handle").all()
        print(f"\n[T3] handle count = {len(handles)}")
        if len(handles) < 2:
            fails.append("T3: handle 渲染数量不足")
        else:
            # 检查第一个 handle 的 opacity
            styles = handles[0].evaluate(
                "el => ({ opacity: getComputedStyle(el).opacity, width: getComputedStyle(el).width })"
            )
            print(f"  [debug] handle default style: {styles}")
            if float(styles["opacity"]) < 0.5:
                fails.append(f"T3: handle 默认 opacity={styles['opacity']} 仍不可见")
            else:
                print(f"  ✅ PASS  (opacity={styles['opacity']}, width={styles['width']})")
        shot(page, "02_handles_visible_by_default")

        # T4: 拖动 source handle -> target handle 创建边
        # 添加第二个节点（generate 类型需要从菜单加，但菜单只有 text/image/video/audio/audio/world3d）
        # 用 image 节点来连
        add_node(page, "image")
        page.wait_for_timeout(400)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        # 找两个节点的 handle
        nodes = page.locator(".react-flow__node").all()
        if len(nodes) < 2:
            fails.append("T4: 节点数量不足 2，无法测连线")
        else:
            # 用 data-handlepos 定位 source (Right) / target (Left)
            src = nodes[0].locator('.react-flow__handle[data-handlepos="right"]').first
            tgt = nodes[1].locator('.react-flow__handle[data-handlepos="left"]').first
            src_box = src.bounding_box()
            tgt_box = tgt.bounding_box()
            print(f"\n[T4] src handle box: {src_box}")
            print(f"     tgt handle box: {tgt_box}")
            # 模拟拖拽：mousedown 在 src，多次 mousemove 拖到 tgt，再 mouseup
            sx = src_box["x"] + src_box["width"]/2
            sy = src_box["y"] + src_box["height"]/2
            tx = tgt_box["x"] + tgt_box["width"]/2
            ty = tgt_box["y"] + tgt_box["height"]/2
            page.mouse.move(sx, sy)
            page.mouse.down()
            steps = 25
            for i in range(1, steps+1):
                ix = sx + (tx - sx) * i / steps
                iy = sy + (ty - sy) * i / steps
                page.mouse.move(ix, iy, steps=2)
                page.wait_for_timeout(20)
            page.mouse.up()
            page.wait_for_timeout(800)
            # 检查边数
            edge_cnt = page.locator(".react-flow__edge").count()
            print(f"     edge count after drag = {edge_cnt}")
            shot(page, "03_after_handle_drag")
            if edge_cnt < 1:
                fails.append(f"T4: 连线失败，边数={edge_cnt}")
            else:
                print("  ✅ PASS")

        # T5: 点击放大按钮改变 zoom
        zoom_before = page.evaluate("() => document.querySelector('.react-flow__viewport').style.transform")
        page.locator(".pea-zoom-controls .pea-zoom-btn[aria-label='放大画布']").first.click()
        page.wait_for_timeout(400)
        page.locator(".pea-zoom-controls .pea-zoom-btn[aria-label='放大画布']").first.click()
        page.wait_for_timeout(400)
        zoom_after = page.evaluate("() => document.querySelector('.react-flow__viewport').style.transform")
        readout = page.locator(".pea-zoom-readout").first.text_content()
        print(f"\n[T5] viewport transform before: {zoom_before}")
        print(f"     viewport transform after : {zoom_after}")
        print(f"     readout text              : {readout}")
        if zoom_before == zoom_after:
            fails.append("T5: 点击放大按钮后 viewport transform 未变化")
        elif not readout or "%" not in readout:
            fails.append(f"T5: 缩放读数异常：{readout}")
        else:
            print(f"  ✅ PASS (readout={readout})")
        shot(page, "04_after_zoom_in")

        # 缩小按钮
        page.locator(".pea-zoom-controls .pea-zoom-btn[aria-label='缩小画布']").first.click()
        page.wait_for_timeout(300)
        readout2 = page.locator(".pea-zoom-readout").first.text_content()
        print(f"     after zoom out readout    : {readout2}")

        # 适配视图按钮
        page.locator(".pea-zoom-controls .pea-zoom-btn[aria-label='适配视图']").first.click()
        page.wait_for_timeout(500)
        readout3 = page.locator(".pea-zoom-readout").first.text_content()
        print(f"     after fit view readout    : {readout3}")
        shot(page, "05_after_fit_view")

        # T6: console errors
        print(f"\n[T6] console errors count = {len(console_errors)}")
        for t, msg in console_errors:
            print(f"     [{t}] {msg[:200]}")
        if console_errors:
            fails.append(f"T6: {len(console_errors)} 个 console error")

        browser.close()

    print("\n" + "=" * 60)
    if fails:
        print("❌ 失败项：")
        for f in fails:
            print(f"   - {f}")
        sys.exit(1)
    print("✅ 全部 PASS")

if __name__ == "__main__":
    main()