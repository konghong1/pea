#!/usr/bin/env python3
"""
复现"缩放滑块让画布回到初始状态"问题。
步骤：
  1. 注册登录，进入工作空间
  2. 点击"新建项目"创建画布（自动跳转画布页）
  3. 添加几个节点
  4. 把画布向右下平移（拖动空白处）让 viewport 偏离初始位置
  5. 用键盘控制缩放滑块改变 zoom
  6. 检查 viewport 中心 flow 坐标在缩放前后是否保持不变
     - 预期（修复后）：中心 flow 坐标不变
     - 现状（bug）：中心 flow 坐标发生显著移动 → 视觉上像"回到初始状态"
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name):
    p = OUT / f"repro_slider_zoom_{name}.png"
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
    return {
        "cx": vp["x"] + (dim["width"] / 2) / vp["zoom"],
        "cy": vp["y"] + (dim["height"] / 2) / vp["zoom"],
    }


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

        # 1) 注册登录（Vite dev server，HMR 拿到最新代码）
        page.goto("http://localhost:5173", wait_until="networkidle")
        page.wait_for_timeout(1000)
        ts = int(time.time() * 1000)
        try:
            page.get_by_role("button", name="没有账号？去注册").first.click()
            page.wait_for_timeout(500)
            page.fill('input[placeholder="you@pea.ai"]', f"repro_{ts}@pea.ai")
            page.fill('input[placeholder="至少 8 位"]', "Password123")
            try:
                page.fill('input[placeholder="可选"]', "REPRO")
            except Exception:
                pass
            page.locator("form button[type=submit]").click()
        except Exception as e:
            print(f"[warn] 注册流程异常（可能已登录）: {e}")
        page.wait_for_timeout(4000)

        # 启用 dev hooks（让 window.__rfStore 暴露）
        page.evaluate("localStorage.setItem('__peaDevHooks', '1')")
        # 切到工作空间
        try:
            page.get_by_role("button", name="工作空间").first.click()
            page.wait_for_timeout(800)
        except Exception:
            pass

        # 2) 新建项目（创建画布并自动跳转）
        try:
            new_btn = page.locator("button.projects-new-btn").first
            new_btn.click()
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"[fail] 找不到'新建项目'按钮: {e}")
            shot(page, "no_new_btn")
            return

        # 等待画布出现
        try:
            page.wait_for_selector(".react-flow__viewport", timeout=15000)
        except Exception:
            print("[fail] 创建项目后未看到 .react-flow__viewport")
            shot(page, "no_canvas")
            return
        page.wait_for_timeout(1500)
        shot(page, "01_empty_canvas")

        # 3) 双击空白处添加几个节点
        rf = page.locator(".react-flow").first
        box = rf.bounding_box()
        for i, (dx, dy) in enumerate([(120, 80), (320, 180), (520, 80)]):
            page.mouse.dblclick(box["x"] + 200 + dx, box["y"] + 200 + dy)
            page.wait_for_timeout(300)
        page.wait_for_timeout(500)
        shot(page, "02_nodes_added")

        # 4) 把画布向右下平移一段距离
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        # 拖动空白区域
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 2 + 200, box["y"] + box["height"] / 2 + 120, steps=20)
        page.mouse.up()
        page.wait_for_timeout(400)
        shot(page, "03_after_pan")

        # 启用 dev hooks 后再 reload 一次确保 __rfStore 暴露
        page.evaluate("localStorage.setItem('__peaDevHooks', '1')")
        vp0 = get_vp(page)
        dim = get_dim(page)
        print(f"[vp after pan] {vp0}  dim={dim}")
        if not vp0 or not dim:
            print("[fail] __rfStore 未暴露，重试 reload")
            page.reload(wait_until="networkidle")
            page.wait_for_selector(".react-flow__viewport", timeout=10000)
            page.wait_for_timeout(1500)
            # 重新平移
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 200, box["y"] + box["height"] / 2 + 120, steps=20)
            page.mouse.up()
            page.wait_for_timeout(400)
            vp0 = get_vp(page)
            dim = get_dim(page)
            print(f"[vp after pan retry] {vp0}  dim={dim}")
        c0 = center_flow(vp0, dim)
        print(f"[center0] cx={c0['cx']:.1f}  cy={c0['cy']:.1f}")

        # 5) 拖动缩放滑块：用键盘改变（更稳定）
        slider = page.locator(".pea-canvas-controls-pill input[type='range']").first
        slider.click()
        page.wait_for_timeout(200)
        # Home → 最小
        page.keyboard.press("Home")
        page.wait_for_timeout(300)
        vp_min = get_vp(page)
        c_min = center_flow(vp_min, dim)
        print(f"[vp after Home] {vp_min}")
        print(f"[center_min] cx={c_min['cx']:.1f}  cy={c_min['cy']:.1f}  Δcx={c_min['cx']-c0['cx']:+.1f}  Δcy={c_min['cy']-c0['cy']:+.1f}")
        shot(page, "04_after_slider_min")

        # 再按几次 → 让 zoom 改变
        for _ in range(10):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(80)
        vp_mid = get_vp(page)
        c_mid = center_flow(vp_mid, dim)
        print(f"[vp after +10 Right] {vp_mid}")
        print(f"[center_mid] cx={c_mid['cx']:.1f}  cy={c_mid['cy']:.1f}  Δcx={c_mid['cx']-c0['cx']:+.1f}  Δcy={c_mid['cy']-c0['cy']:+.1f}")
        shot(page, "05_after_slider_right")

        moved = abs(c_min["cx"] - c0["cx"]) > 30 or abs(c_min["cy"] - c0["cy"]) > 30
        moved_mid = abs(c_mid["cx"] - c0["cx"]) > 30 or abs(c_mid["cy"] - c0["cy"]) > 30
        print()
        if moved or moved_mid:
            print(f"[bug 复现] 缩放后画布中心 flow 坐标发生显著移动（|Δ| > 30px）→ 视觉上'回到初始状态'")
            if moved:
                print(f"  Home:  Δcx={c_min['cx']-c0['cx']:+.1f}  Δcy={c_min['cy']-c0['cy']:+.1f}")
            if moved_mid:
                print(f"  +10:   Δcx={c_mid['cx']-c0['cx']:+.1f}  Δcy={c_mid['cy']-c0['cy']:+.1f}")
        else:
            print(f"[ok] 缩放后画布中心 flow 坐标基本保持不变")

        browser.close()


if __name__ == "__main__":
    main()
