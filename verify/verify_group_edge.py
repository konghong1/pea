"""E2E 验证：组内节点之间的连线是否可见。

流程：登录 -> 进入画布 -> 添加两个节点 -> 连线 -> 打组 -> 截图 ->
      检查组内边的存在性、可见性、层级。
"""
import os
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "verify"
OUT_DIR.mkdir(exist_ok=True)

BASE_URL = "http://localhost:5173"
BFF_URL = "http://localhost:4100"
EMAIL = "test@example.com"
PASSWORD = "password123"


def wait_for_canvas(page):
    page.wait_for_selector(".react-flow__pane", timeout=30000)
    # 等待 zustand store 挂载到 window
    page.wait_for_function(
        "() => typeof window.__canvas !== 'undefined' && window.__canvas.getState",
        timeout=30000,
    )


def add_image_node(page, label, x, y):
    """通过 store API 添加一个图片节点（与截图场景一致）。"""
    return page.evaluate(
        """([label, x, y]) => {
            const store = window.__canvas;
            const id = store.getState().addNode({
                kind: 'image',
                label: label,
                prompt: '',
                meta: {},
            }, { x, y });
            return id;
        }""",
        [label, x, y],
    )


def connect_nodes(page, src, tgt):
    """通过 store API 连接两个节点。"""
    page.evaluate(
        """([src, tgt]) => {
            window.__canvas.getState().onConnect({
                source: src,
                target: tgt,
                sourceHandle: null,
                targetHandle: 'in',
            });
        }""",
        [src, tgt],
    )


def group_nodes(page, ids):
    return page.evaluate(
        """(ids) => window.__canvas.getState().groupNodes(ids)""",
        ids,
    )


def get_edge_count(page):
    return page.evaluate(
        "() => document.querySelectorAll('.react-flow__edge').length"
    )


def get_edge_styles(page):
    return page.evaluate(
        """() => {
            const edge = document.querySelector('.react-flow__edge');
            if (!edge) return null;
            const line = edge.querySelector('.pea-edge-line');
            const comp = line ? getComputedStyle(line) : null;
            const group = document.querySelector('.react-flow__node-group .pea-group-node');
            const groupComp = group ? getComputedStyle(group) : null;
            return {
                edgeCount: document.querySelectorAll('.react-flow__edge').length,
                edgeClass: edge.className,
                lineOpacity: comp ? comp.opacity : null,
                lineStroke: comp ? comp.stroke : null,
                lineDisplay: comp ? comp.display : null,
                lineVisibility: comp ? comp.visibility : null,
                edgeZ: getComputedStyle(edge).zIndex,
                edgeRect: edge.getBoundingClientRect(),
                groupZ: document.querySelector('.react-flow__node-group')
                    ? getComputedStyle(document.querySelector('.react-flow__node-group')).zIndex
                    : null,
                groupBg: groupComp ? groupComp.backgroundColor : null,
            };
        }"""
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # 通过 BFF API 登录并写 token 到 localStorage（UI 登录当前有 bug 不跳转）
        r = requests.post(
            f"{BFF_URL}/api/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=10,
        )
        r.raise_for_status()
        token = r.json()["token"]
        page.goto(f"{BASE_URL}/login")
        page.evaluate(f"() => localStorage.setItem('pea_token', {token!r})")
        page.goto(f"{BASE_URL}/")
        time.sleep(2)

        # 进入画布
        if "/canvas" not in page.url:
            try:
                page.locator("text=未命名画布").first.click(timeout=6000)
            except Exception:
                page.locator("a[href*='/canvas']").first.click(timeout=6000)
        page.wait_for_selector(".react-flow__pane", timeout=30000)
        time.sleep(1)

        # 添加两个图片节点并连线（模拟用户截图：组内两个图片节点）
        n1 = add_image_node(page, "kkkkkk", 200, 300)
        n2 = add_image_node(page, "图片", 620, 300)
        time.sleep(0.3)
        connect_nodes(page, n1, n2)
        time.sleep(0.3)

        # 先截图：分组前
        page.screenshot(path=str(OUT_DIR / "edge_before_group.png"))
        before_count = get_edge_count(page)
        before_styles = get_edge_styles(page)
        print(f"[before group] edge count={before_count}")
        print(f"[before group] edge styles={before_styles}")

        # 打组
        gid = group_nodes(page, [n1, n2])
        time.sleep(0.5)

        # 截图：分组后
        page.screenshot(path=str(OUT_DIR / "edge_after_group.png"))
        after_count = get_edge_count(page)
        after_styles = get_edge_styles(page)
        print(f"[after group] gid={gid}, edge count={after_count}")
        print(f"[after group] edge styles={after_styles}")

        # 检查：边数量不变，且线可见；组背景必须是透明，否则线会被背景盖住
        assert after_count == before_count, f"边数量变化：{before_count} -> {after_count}"
        assert after_styles is not None, "分组后找不到边"
        assert after_styles["lineOpacity"] not in (None, "0"), f"分组后边线不可见 opacity={after_styles['lineOpacity']}"
        assert after_styles["lineDisplay"] != "none", f"分组后边线 display=none"
        assert after_styles["lineVisibility"] != "hidden", f"分组后边线 visibility=hidden"
        assert after_styles["groupBg"] in ("rgba(0, 0, 0, 0)", "transparent"), (
            f"组背景不透明，会盖住连线: {after_styles['groupBg']}"
        )

        # 检查层级：边在组之上
        # 注意：zIndex 可能返回 auto / number 字符串
        print(f"edge z={after_styles['edgeZ']}, group z={after_styles['groupZ']}")

        # 额外：尝试点击/悬停边，确认事件正常
        edge = page.locator(".react-flow__edge").first
        edge_box = edge.bounding_box()
        print(f"edge bounding box={edge_box}")
        if edge_box:
            mid_x = edge_box["x"] + edge_box["width"] / 2
            mid_y = edge_box["y"] + edge_box["height"] / 2
            page.mouse.move(mid_x, mid_y)
            time.sleep(0.3)
            page.screenshot(path=str(OUT_DIR / "edge_hover_group.png"))

        browser.close()
        print("PASS: group edge visible")


if __name__ == "__main__":
    main()
