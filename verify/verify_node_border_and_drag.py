"""
验证两个高频回归：
  1) 点击节点 → 边框输入栏（node-input-bar）必须弹出；
     规则：AI 生成节点（有 resultUrl）/ 文本节点 要展示，
           自己上传的节点（有 fileKey 无 resultUrl）不展示。
  2) 文本节点：单击选中后可拖动（之前因 nodrag 常驻导致拖不动）。
通过 window.__canvas dev hook 注入确定节点，避免 UI 时序干扰。
"""
import time
from playwright.sync_api import sync_playwright, expect
from pathlib import Path

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
BASE = "http://localhost:8088"

errors: list[str] = []


def on_console(msg):
    if msg.type == "error":
        errors.append(f"{msg.type}: {msg.text}")


def on_pageerror(err):
    errors.append(f"pageerror: {err}")


def ensure_canvas(page):
    """确保在画布视图：若未进入（在工作空间），点击新建项目。"""
    if page.locator(".react-flow__viewport").count() == 0:
        page.get_by_role("button", name="新建项目").first.click()
        page.wait_for_timeout(1500)
    page.wait_for_selector(".react-flow__viewport", timeout=20000)


def node_box(page, nid):
    return page.locator(f".react-flow__node[data-id='{nid}']").bounding_box()


def node_class(page, nid):
    return (page.locator(f".react-flow__node[data-id='{nid}'] .pea-node").get_attribute("class") or "")


def pos_of(page, nid):
    return page.evaluate(
        f"(() => {{ const n = window.__canvas.getState().nodes.find(x => x.id==='{nid}'); return n ? n.position : null; }})()"
    )


def main():
    GRAPH = [
        {"id": "t1", "type": "pea", "position": {"x": 360, "y": 150},
         "data": {"kind": "text", "html": "<p>双击编辑文本</p>", "label": "Text"}},
        {"id": "ai1", "type": "pea", "position": {"x": 820, "y": 150},
         "data": {"kind": "image", "resultUrl": "https://placehold.co/320x320/1c1c24/0bf?text=AI",
                  "prompt": "一只戴墨镜的猫", "label": "Image"}},
        {"id": "up1", "type": "pea", "position": {"x": 360, "y": 470},
         "data": {"kind": "image", "url": "https://placehold.co/320x320/444/fff?text=Upload",
                  "fileKey": "upload-test-key-123", "label": "Upload"}},
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        # ---- 登录（沿用既有注册流）----
        print("[1] 注册并进入工作空间 ...")
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"vnbd_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "VNBD")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4500)
        ensure_canvas(page)
        print("    ✅ 已进入画布")

        # ---- 开启 dev hook 并刷新，暴露 window.__canvas ----
        print("[2] 开启 dev hook 并刷新 ...")
        page.evaluate("localStorage.setItem('__peaDevHooks','1')")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        ensure_canvas(page)
        page.wait_for_function("() => window.__canvas && window.__canvas.getState", timeout=15000)

        # ---- 注入确定节点 ----
        print("[3] 注入 3 个测试节点 (text / AI图片 / 上传图片) ...")
        page.evaluate(
            """(g) => { const s = window.__canvas.getState(); s.loadGraph(g, [], s.version); }""",
            GRAPH,
        )
        page.wait_for_timeout(900)
        page.wait_for_selector(".react-flow__node[data-id='t1']", timeout=8000)
        page.wait_for_selector(".react-flow__node[data-id='ai1']", timeout=8000)
        page.wait_for_selector(".react-flow__node[data-id='up1']", timeout=8000)
        print("    ✅ 3 个节点已注入")

        bar = page.locator(".node-input-bar")

        # ===== 测试1：AI 生成节点点击 → 输入栏弹出 =====
        print("\n[4] 点击 AI 生成节点 ai1 → 输入栏应弹出 ...")
        b = node_box(page, "ai1")
        page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        page.wait_for_timeout(600)
        expect(bar).to_be_visible(timeout=3000)
        cls = node_class(page, "ai1")
        assert "selected" in cls, f"ai1 未获得 selected 类: {cls}"
        bb = bar.bounding_box()
        print(f"    ✅ ai1 输入栏已弹出，节点带 selected 边框 ({bb['width']:.0f}x{bb['height']:.0f})")
        page.screenshot(path=str(SHOTS / "vnbd_ai1_box.png"))

        # ===== 测试2：自己上传节点点击 → 输入栏不弹出 =====
        print("\n[5] 点击自己上传节点 up1 → 输入栏不应弹出 ...")
        b = node_box(page, "up1")
        page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        page.wait_for_timeout(600)
        cnt = bar.count()
        cls = node_class(page, "up1")
        assert "selected" in cls, f"up1 未获得 selected 类: {cls}"
        assert cnt == 0, f"上传节点不应弹出输入栏，但检测到 {cnt} 个 .node-input-bar"
        print(f"    ✅ up1 已选中但无输入栏（符合上传节点规则），bar 数={cnt}")
        page.screenshot(path=str(SHOTS / "vnbd_up1_nobox.png"))

        # ===== 测试3：文本节点点击 → 输入栏弹出，且可拖动 =====
        print("\n[6] 点击文本节点 t1 → 输入栏弹出 ...")
        b = node_box(page, "t1")
        page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        page.wait_for_timeout(600)
        expect(bar).to_be_visible(timeout=3000)
        print("    ✅ t1 输入栏已弹出")
        page.screenshot(path=str(SHOTS / "vnbd_t1_box.png"))

        print("\n[7] 拖动文本节点 t1（验证 nodrag 回归修复）...")
        pos0 = pos_of(page, "t1")
        cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        page.mouse.move(cx, cy)
        page.mouse.down()
        page.mouse.move(cx + 130, cy + 80, steps=12)
        page.mouse.up()
        page.wait_for_timeout(600)
        pos1 = pos_of(page, "t1")
        dx = pos1["x"] - pos0["x"]
        dy = pos1["y"] - pos0["y"]
        print(f"    位置变化: dx={dx:.1f} dy={dy:.1f}")
        assert abs(dx) > 15 or abs(dy) > 15, f"文本节点拖动无效，位移过小 dx={dx}, dy={dy}"
        print(f"    ✅ 文本节点成功拖动 (位移 {abs(dx):.0f},{abs(dy):.0f})")
        page.screenshot(path=str(SHOTS / "vnbd_t1_dragged.png"))

        # ---- 控制台错误 ----
        print("\n[8] 控制台错误检查 ...")
        if errors:
            print(f"    ⚠️ {len(errors)} 条控制台错误(前8):")
            for e in errors[:8]:
                print(f"      {e[:160]}")
        else:
            print("    ✅ 零控制台错误")

        browser.close()
        print("\n🎉 全部通过：输入栏按规则弹出/隐藏，文本节点可拖动。")


if __name__ == "__main__":
    main()
