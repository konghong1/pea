#!/usr/bin/env python3
"""
完整验证：平移 + 滑块缩放，画布视觉中心应保持稳定。
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent


def shot(page, name):
    p = OUT / f"verify_slider_zoom_fix_{name}.png"
    page.screenshot(path=str(p))
    print(f"  [shot] {p.name}")


def get_vp(page):
    return page.evaluate(
        """() => {
          const s = window.__rfStore;
          if (!s) return null;
          const t = s.getState().transform;
          return { x: t[0], y: t[1], zoom: t[2] };
        }"""
    )


def get_dim(page):
    return page.evaluate(
        """() => {
          const s = window.__rfStore;
          if (!s) return null;
          return { width: s.getState().width, height: s.getState().height };
        }"""
    )


def center_flow(vp, dim):
    # ReactFlow 变换：screen = flow * zoom + translate
    # => flow = (screen - translate) / zoom；屏幕中心对应 flow 坐标：
    return {
        "cx": (dim["width"] / 2 - vp["x"]) / vp["zoom"],
        "cy": (dim["height"] / 2 - vp["y"]) / vp["zoom"],
    }


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

        # 登录
        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(1000)
        ts = int(time.time() * 1000)
        try:
            page.get_by_role("button", name="没有账号？去注册").first.click()
            page.wait_for_timeout(400)
            page.fill('input[placeholder="you@pea.ai"]', f"vp_{ts}@pea.ai")
            page.fill('input[placeholder="至少 8 位"]', "Password123")
            try:
                page.fill('input[placeholder="可选"]', "VPTEST")
            except Exception:
                pass
            page.locator("form button[type=submit]").click()
        except Exception:
            pass
        page.wait_for_timeout(4000)

        # dev hooks
        page.evaluate("localStorage.setItem('__peaDevHooks', '1')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(800)

        # 创建画布
        try:
            page.get_by_role("button", name="工作空间").first.click()
            page.wait_for_timeout(400)
        except Exception:
            pass
        try:
            page.locator("button.projects-new-btn").first.click()
        except Exception:
            print("[fail] 找不到新建项目按钮")
            return
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(1500)

        # 通过工具栏添加节点：点击 + 选"文本"
        try:
            page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
            page.wait_for_selector(".pea-add-menu", timeout=4000)
            page.locator(".pea-add-menu-item:has-text('文本')").first.click()
            page.wait_for_timeout(400)
            # 再加 2 个
            page.mouse.move(10, 10)
            page.wait_for_timeout(200)
            page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
            page.wait_for_selector(".pea-add-menu", timeout=4000)
            page.locator(".pea-add-menu-item:has-text('文本')").first.click()
            page.wait_for_timeout(400)
            page.mouse.move(10, 10)
            page.wait_for_timeout(200)
            page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first.click(force=True)
            page.wait_for_selector(".pea-add-menu", timeout=4000)
            page.locator(".pea-add-menu-item:has-text('文本')").first.click()
            page.wait_for_timeout(400)
            page.mouse.move(10, 10)
            page.wait_for_timeout(300)
        except Exception as e:
            print(f"[warn] 加节点失败: {e}")

        # 取消选中
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        shot(page, "01_nodes_in")

        # 启用 dev hooks 重新加载
        page.evaluate("localStorage.setItem('__peaDevHooks', '1')")
        page.wait_for_timeout(500)

        # 拿尺寸
        dim = get_dim(page)
        print(f"canvas dim: {dim}")

        # 多次平移让 viewport 远离初始
        rf = page.locator(".react-flow").first
        box = rf.bounding_box()
        for i in range(4):
            page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.6)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * 0.6 + 150, box["y"] + box["height"] * 0.6 + 80, steps=20)
            page.mouse.up()
            page.wait_for_timeout(200)

        vp0 = get_vp(page)
        c0 = center_flow(vp0, dim)
        print(f"[after pan]  vp={vp0}  center_flow=({c0['cx']:.1f}, {c0['cy']:.1f})")
        shot(page, "02_after_pan")

        # 用键盘操作滑块
        slider = page.locator(".pea-canvas-controls-pill input[type='range']").first
        slider.click()
        page.wait_for_timeout(200)

        # 缩小到 0.25
        page.keyboard.press("Home")
        page.wait_for_timeout(300)
        vp1 = get_vp(page)
        c1 = center_flow(vp1, dim)
        print(f"[Home→0.25]  vp={vp1}  center_flow=({c1['cx']:.1f}, {c1['cy']:.1f})  Δcx={c1['cx']-c0['cx']:+.1f}  Δcy={c1['cy']-c0['cy']:+.1f}")
        shot(page, "03_zoom_min")

        # 放大到 3.0
        page.keyboard.press("End")
        page.wait_for_timeout(300)
        vp2 = get_vp(page)
        c2 = center_flow(vp2, dim)
        print(f"[End→3.0]    vp={vp2}  center_flow=({c2['cx']:.1f}, {c2['cy']:.1f})  Δcx={c2['cx']-c0['cx']:+.1f}  Δcy={c2['cy']-c0['cy']:+.1f}")
        shot(page, "04_zoom_max")

        # 中间 1.0
        page.keyboard.press("Home")
        page.wait_for_timeout(200)
        for _ in range(40):
            page.keyboard.press("ArrowRight")
        page.wait_for_timeout(300)
        vp3 = get_vp(page)
        c3 = center_flow(vp3, dim)
        print(f"[mid ~1.0]   vp={vp3}  center_flow=({c3['cx']:.1f}, {c3['cy']:.1f})  Δcx={c3['cx']-c0['cx']:+.1f}  Δcy={c3['cy']-c0['cy']:+.1f}")
        shot(page, "05_zoom_mid")

        # 判定
        max_dx = max(abs(c1['cx']-c0['cx']), abs(c2['cx']-c0['cx']), abs(c3['cx']-c0['cx']))
        max_dy = max(abs(c1['cy']-c0['cy']), abs(c2['cy']-c0['cy']), abs(c3['cy']-c0['cy']))
        print()
        if max_dx < 5 and max_dy < 5:
            print(f"[PASS] 三种 zoom 级别下，画布视觉中心 flow 坐标保持稳定（最大漂移 {max_dx:.1f}, {max_dy:.1f}）")
        else:
            print(f"[FAIL] 视觉中心漂移过大：Δcx={max_dx:.1f}  Δcy={max_dy:.1f}")

        browser.close()


if __name__ == "__main__":
    main()
