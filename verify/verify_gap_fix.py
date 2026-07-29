"""验证 v4: 正确连线 + 精确测量 + 弹回测试"""
import asyncio, time, os, json
from playwright.async_api import async_playwright

SHOTS = "C:/workspace/pea/verify"
os.makedirs(SHOTS, exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        BASE = "http://localhost:8088"

        await page.goto(BASE, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1000)

        # 注册
        reg_btn = page.get_by_role("button", name="没有账号？去注册")
        if await reg_btn.count() > 0:
            await reg_btn.first.click()
            await page.wait_for_timeout(500)
            ts = int(time.time())
            await page.fill('input[placeholder="you@pea.ai"]', f"v4_{ts}@pea.dev")
            await page.fill('input[placeholder="至少 8 位"]', "Password123")
            nick = page.locator('input[placeholder="可选"]')
            if await nick.count() > 0:
                await nick.fill("V4")
            submit = page.locator('form button[type=submit]')
            if await submit.count() > 0:
                await submit.click()
                await page.wait_for_timeout(4000)

        # 新建项目
        new_proj = page.locator("text=新建项目")
        if await new_proj.count() > 0:
            await new_proj.first.click()
            await page.wait_for_timeout(3000)

        try:
            await page.wait_for_selector(".react-flow__viewport", timeout=15000)
        except:
            print("FAIL: no canvas")
            await browser.close()
            return

        # 添加两个图片节点
        toolbar = page.locator(".pea-toolbar")
        if await toolbar.count() > 0:
            add_btn = toolbar.get_by_role("button", name="添加节点")
            for _ in range(2):
                if await add_btn.count() > 0:
                    await add_btn.first.click()
                    await page.wait_for_timeout(400)
                    item = page.locator(".pea-add-menu-item", has_text="图片")
                    if await item.count() > 0:
                        await item.first.click()
                        await page.wait_for_timeout(600)

        await page.wait_for_timeout(1000)
        nodes = page.locator(".react-flow__node")
        cnt = await nodes.count()
        if cnt < 2:
            print(f"FAIL: only {cnt} nodes")
            await browser.close()
            return

        b1 = await nodes.nth(0).bounding_box()
        b2 = await nodes.nth(1).bounding_box()
        if not b1 or not b2:
            await browser.close()
            return

        n1cx = b1["x"] + b1["width"] / 2
        n1cy = b1["y"] + b1["height"] / 2
        n2cx = b2["x"] + b2["width"] / 2
        n2cy = b2["y"] + b2["height"] / 2

        # ── Step 1: hover node1 让 handle 出现 ──
        await page.mouse.move(n1cx, n1cy)
        await page.wait_for_timeout(700)

        # 用 JS 强制让 handle 可见并获取精确坐标
        handle_pos = await page.evaluate('''([x1, y1, w1, h1, x2, y2, w2, h2]) => {
            // 给 .pea-node 加 hover class 让 handle 显示
            document.querySelectorAll('.pea-node').forEach(n => n.classList.add('hover'));
            
            const handles = document.querySelectorAll('.react-flow__handle.pea-handle');
            const positions = [];
            handles.forEach((h, i) => {
                const r = h.getBoundingClientRect();
                // 强制可见以便点击
                h.style.opacity = '1';
                h.style.pointerEvents = 'all';
                positions.push({
                    i,
                    cx: r.left + r.width / 2,
                    cy: r.top + r.height / 2,
                    visible: true
                });
            });
            return positions;
        }''', [b1["x"], b1["y"], b1["width"], b1["height"],
          b2["x"], b2["y"], b2["width"], b2["height"]])

        print(f"Handles found: {len(handle_pos)}")
        for h in handle_pos:
            print(f"  [{h['i']}] cx={h['cx']:.1f} cy={h['cy']:.1f}")

        # ── Step 2: 从 node1 右 handle 拖到 node2 左 handle ──
        if len(handle_pos) >= 2:
            # 找 node1 的右 handle (source) 和 node2 的左 handle (target)
            src = None  # node1 右侧的 handle (cx > n1cx)
            dst = None  # node2 左侧的 handle (cx < n2cx)
            for h in handle_pos:
                if h["cx"] > n1cx and abs(h["cy"] - n1cy) < 50:
                    src = h
                if h["cx"] < n2cx and abs(h["cy"] - n2cy) < 50:
                    dst = h

            if src and dst:
                print(f"\nConnect: ({src['cx']:.0f},{src['cy']:.0f}) -> ({dst['cx']:.0f},{dst['cy']:.0f})")
                # 用真实鼠标事件拖拽
                await page.mouse.move(src["cx"], src["cy"])
                await page.wait_for_timeout(300)
                await page.mouse.down()
                await page.wait_for_timeout(200)
                # 逐步移动到目标
                await page.mouse.move(dst["cx"], dst["cy"], steps=15)
                await page.wait_for_timeout(300)
                await page.mouse.up()
                await page.wait_for_timeout(1500)

        # ── 截图：带连线的画布 ──
        await page.screenshot(path=f"{SHOTS}/v4_connected.png")
        print("\n[SHOT] v4_connected.png")

        # ── 测量：handle 与节点框实际距离 ──
        gap_data = await page.evaluate('''() => {
            const results = [];
            document.querySelectorAll('.pea-node').forEach((node, ni) => {
                const nRect = node.getBoundingClientRect();
                const handles = node.querySelectorAll(':scope > .react-flow__handle.pea-handle');
                handles.forEach((h, hi) => {
                    const r = h.getBoundingClientRect();
                    const isLeft = h.classList.contains('pea-handle-left');
                    let gap;
                    if (isLeft) {
                        gap = nRect.left - (r.left + r.width/2);
                    } else {
                        gap = (r.left + r.width/2) - nRect.right;
                    }
                    results.push({
                        node: ni,
                        side: isLeft ? 'L' : 'R',
                        gapPx: Math.round(gap * 10) / 10,
                        handleSize: `${Math.round(r.width)}x${Math.round(r.height)}`
                    });
                });
            });
            return results;
        }''')

        print("\n=== Handle Gap Measurement ===")
        for g in gap_data:
            print(f"  Node{g['node']} {g['side']}: gap={g['gapPx']}px (size={g['handleSize']})")

        # ── 弹回测试：hover + 移动到热区 ──
        # 先移开鼠标重置
        await page.mouse.move(100, 100)
        await page.wait_for_timeout(400)

        # 再 hover node1
        await page.mouse.move(n1cx, n1cy)
        await page.wait_for_timeout(600)

        # 鼠标移到右 handle 外侧（远离节点）
        outer_x = b1["x"] + b1["width"] + 25
        await page.mouse.move(outer_x, n1cy)
        await page.wait_for_timeout(500)
        vars_outer = await page.evaluate('''() => {
            const el = document.querySelector('.pea-node.hover');
            return el ? {
                hx_l: getComputedStyle(el).getPropertyValue('--pea-hx-l').trim(),
                hy_l: getComputedStyle(el).getPropertyValue('--pea-hy-l').trim(),
                hx_r: getComputedStyle(el).getPropertyValue('--pea-hx-r').trim(),
                hy_r: getComputedStyle(el).getPropertyValue('--pea-hy-r').trim(),
            } : null;
        }''')
        print(f"\n=== Mouse OUTSIDE (far from node) ===")
        print(f"  Vars: {json.dumps(vars_outer)}")

        # 鼠标移到右 handle 内侧（朝向节点，测试弹回）
        inner_x = b1["x"] + b1["width"] - 3  # 几乎进节点框
        await page.mouse.move(inner_x, n1cy)
        await page.wait_for_timeout(500)
        vars_inner = await page.evaluate('''() => {
            const el = document.querySelector('.pea-node.hover');
            return el ? {
                hx_l: getComputedStyle(el).getPropertyValue('--pea-hx-l').trim(),
                hy_l: getComputedStyle(el).getPropertyValue('--pea-hy-l').trim(),
                hx_r: getComputedStyle(el).getPropertyValue('--pea-hx-r').trim(),
                hy_r: getComputedStyle(el).getPropertyValue('--pea-hy-r').trim(),
            } : null;
        }''')
        print(f"\n=== Mouse INSIDE node edge (bounce-back test) ===")
        print(f"  Vars: {json.dumps(vars_inner)}")

        # 判断弹回是否生效：hx_r 应该 <= GAP_SCREEN (不能进入节点)
        try:
            hr_inner = float(vars_inner.get("hx_r", "0").replace("px", ""))
            if hr_inner <= 2.1:  # GAP=2 + 小误差
                print(f"  ✅ BOUNCE-BACK OK: hx_r={hr_inner} (clamped at edge)")
            else:
                print(f"  ⚠️ BOUNCE-BACK ISSUE: hx_r={hr_inner} (may have entered node)")
        except:
            pass

        await page.screenshot(path=f"{SHOTS}/v4_bounce_test.png")
        print(f"\n[SHOT] v4_bounce_test.png")
        print("[DONE]")
        await browser.close()

asyncio.run(main())
