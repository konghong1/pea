"""验证画布缩放条以当前可视窗口中心为锚点，不会导致画布跳飞。

测试思路：
1. 注册登录并进入画布，添加一个文本节点并 fitView 让节点位于视口中央。
2. 记录缩放前的 viewport transform（translate + scale）。
3. 用滑块把缩放调到约 50%（放大）和约 25%（缩小）。
4. 根据"中心锚点"公式，用缩放前的 translate/scale、容器尺寸、目标 scale
   计算期望的 translate，与实际 transform 对比。
5. 若两者差值 < 2px，说明缩放锚点是窗口中心；若差值巨大，说明旧 bug 复现。
"""

import sys
import time
import math
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

SHOTS = Path(__file__).resolve().parent / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
errors: list[str] = []
console_msgs: list[str] = []


def on_console(msg):
    if msg.type == "error":
        errors.append(f"console.error: {msg.text}")
    console_msgs.append(f"[{msg.type}] {msg.text}")


def on_pageerror(err):
    errors.append(f"pageerror: {err}")


def shot(page, name: str):
    p = SHOTS / f"zcenter_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"[shot] {p.name}")


def parse_transform(transform: str):
    """从 'translate(123px, 456px) scale(0.78)' 中解析 translate/scale。"""
    m = __import__("re").search(
        r"translate\(\s*(-?[\d.]+)px\s*,\s*(-?[\d.]+)px\s*\)\s*scale\(\s*(-?[\d.]+)\s*\)",
        transform,
    )
    if not m:
        return None
    return {"x": float(m.group(1)), "y": float(m.group(2)), "zoom": float(m.group(3))}


def get_viewport(page):
    return page.evaluate(
        """() => {
            const el = document.querySelector('.react-flow__viewport');
            return el ? el.style.transform : '';
        }"""
    )


def expected_centered_translate(vp, width, height, next_zoom):
    """以窗口中心为锚点，由旧 viewport 推算缩放后的 translate。"""
    w2, h2 = width / 2, height / 2
    cx = (w2 - vp["x"]) / vp["zoom"]
    cy = (h2 - vp["y"]) / vp["zoom"]
    return {"x": w2 - cx * next_zoom, "y": h2 - cy * next_zoom, "zoom": next_zoom}


def move_slider_to(page, slider, ratio: float):
    """点击滑条 ratio 位置（0~1）。"""
    box = slider.bounding_box()
    x = box["x"] + box["width"] * ratio
    y = box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.up()
    page.wait_for_timeout(500)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        # 打开登录页并注册
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"zcenter_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "ZC")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        # 新用户登录后进入项目列表，需要新建/打开一个项目才能进入画布
        page.locator("button", has_text="新建项目").first.click()
        page.wait_for_timeout(2000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        shot(page, "01_initial")

        # 添加一个节点，fitView 使其大致居中
        page.locator('.pea-toolbar .pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(800)
        page.locator(".pea-add-menu-item", has_text="文本").first.click()
        page.wait_for_timeout(800)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        controls = page.locator(".pea-canvas-controls")
        controls.locator("button[title='适配视图 (F)']").click()
        page.wait_for_timeout(700)
        shot(page, "02_after_fitview")

        # 获取容器尺寸（ReactFlow 渲染区）
        flow_box = page.locator(".pea-canvas-flow").first.bounding_box()
        width = flow_box["width"]
        height = flow_box["height"]
        print(f"[info] flow container size: {width:.0f}x{height:.0f}")

        slider = controls.locator("input[type='range']").first
        expect(slider).to_be_visible()

        # 记录缩放前状态
        before_transform = get_viewport(page)
        before = parse_transform(before_transform)
        print(f"[info] before transform: {before_transform}")
        if not before:
            errors.append("无法解析缩放前 viewport transform")
            browser.close()
            raise SystemExit(1)

        # ---- 测试 1：拖到约 75% 位置（放大） ----
        move_slider_to(page, slider, 0.75)
        after_transform = get_viewport(page)
        after = parse_transform(after_transform)
        print(f"[info] after 75% transform: {after_transform}")
        shot(page, "03_zoom_75")
        if after:
            expected = expected_centered_translate(before, width, height, after["zoom"])
            dx = abs(after["x"] - expected["x"])
            dy = abs(after["y"] - expected["y"])
            print(
                f"[check] 75% zoom: expected=({expected['x']:.1f},{expected['y']:.1f}), "
                f"actual=({after['x']:.1f},{after['y']:.1f}), diff=({dx:.1f},{dy:.1f})"
            )
            if dx > 2 or dy > 2:
                errors.append(f"75% 缩放未以窗口中心为锚点：diff=({dx:.1f},{dy:.1f})")
        else:
            errors.append("无法解析 75% 缩放后 viewport transform")

        # ---- 测试 2：拖到约 25% 位置（缩小） ----
        # 以当前状态为基准继续测试
        mid_transform = get_viewport(page)
        mid = parse_transform(mid_transform)
        move_slider_to(page, slider, 0.25)
        after2_transform = get_viewport(page)
        after2 = parse_transform(after2_transform)
        print(f"[info] after 25% transform: {after2_transform}")
        shot(page, "04_zoom_25")
        if mid and after2:
            expected2 = expected_centered_translate(mid, width, height, after2["zoom"])
            dx = abs(after2["x"] - expected2["x"])
            dy = abs(after2["y"] - expected2["y"])
            print(
                f"[check] 25% zoom: expected=({expected2['x']:.1f},{expected2['y']:.1f}), "
                f"actual=({after2['x']:.1f},{after2['y']:.1f}), diff=({dx:.1f},{dy:.1f})"
            )
            if dx > 2 or dy > 2:
                errors.append(f"25% 缩放未以窗口中心为锚点：diff=({dx:.1f},{dy:.1f})")
        else:
            errors.append("无法解析 25% 缩放后 viewport transform")

        # ---- 测试 3：点击滑条不同位置多次，节点不应跳飞出视口 ----
        node = page.locator(".react-flow__node").first
        node_box_before = node.bounding_box()
        for ratio in [0.6, 0.4, 0.8, 0.3]:
            move_slider_to(page, slider, ratio)
        node_box_after = node.bounding_box()
        print(
            f"[check] node screen position before: ({node_box_before['x']:.0f},{node_box_before['y']:.0f}), "
            f"after multiple zooms: ({node_box_after['x']:.0f},{node_box_after['y']:.0f})"
        )
        # 多次缩放后节点应该仍在视口内（坐标在 ±5000 内视为未"跑掉"）
        if abs(node_box_after["x"]) > 5000 or abs(node_box_after["y"]) > 5000:
            errors.append("多次缩放后节点已跳飞出可视区域")
        shot(page, "05_after_multiple_zooms")

        browser.close()

    print("\n" + "=" * 60)
    print(f"[TOTAL ERRORS] {len(errors)}")
    for e in errors:
        print(f"  - {e}")
    if errors:
        sys.exit(1)
    print("✅ 缩放条以窗口中心为锚点，画布未跳飞")


if __name__ == "__main__":
    main()
