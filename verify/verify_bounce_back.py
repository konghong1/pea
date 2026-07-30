"""验证 Issue A：连接点被光标往节点框里推时应当「弹回」到框边，不得进入节点框。
同时顺带确认 Issue B：连接点随画布缩放（zoom 越大视觉越大、越小视觉越小）。
"""
import time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.add_init_script("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}")
        page.set_default_timeout(20000)
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"bounce_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "Bounce")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        try:
            page.get_by_role("button", name="新建项目").first.click()
            page.wait_for_timeout(3000)
            for _ in range(5):
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

        # 取节点 A 的 box 与 source handle，模拟把光标推到框里不同深度
        def measure(handle_side):
            return page.evaluate("""(side) => {
            const n = document.querySelectorAll('.react-flow__node')[0];
            const h = side==='right' ? n.querySelector('.react-flow__handle.source')
                                      : n.querySelector('.react-flow__handle.target');
            if (!h) return null;
            const r = h.getBoundingClientRect();
            // 与弹回判定一致：以 .pea-node（手柄的 offset parent，等同于 body-card 外框）为节点框参考
            const nodeEl = n.querySelector('.pea-node') || n;
            const node = nodeEl.getBoundingClientRect();
                return {
                    handleLeft: r.left, handleRight: r.right, handleCx: r.left + r.width/2,
                    nodeLeft: node.left, nodeRight: node.right,
                    handleW: r.width,
                };
            }""", handle_side)

        a_box = page.locator(".react-flow__node").nth(0).bounding_box()
        cx0 = a_box["x"] + a_box["width"] / 2
        cy0 = a_box["y"] + a_box["height"] / 2

        # 悬停节点 A
        page.mouse.move(cx0, cy0)
        page.wait_for_timeout(300)

        # 把光标推到框「内部」不同深度（距右缘 -5 / -25 / -60 px）
        results = []
        for push_in in [5, 25, 60]:
            px = a_box["x"] + a_box["width"] - push_in
            page.mouse.move(px, cy0, steps=4)
            page.wait_for_timeout(200)
            m = measure("right")
            # 弹回判定：source 手柄左缘不得越过节点右缘（不得进入框内）
            inside = m["handleLeft"] < m["nodeRight"]
            results.append({"push_in": push_in, "measure": m, "handle_inside_box": inside})
            page.screenshot(path=str(SHOTS / f"bounce_push{push_in}.png"))

        # 缩放到 2x，再推一次，确认手柄随缩放放大且仍不进框
        page.evaluate("() => { if (window.__peaSetZoom) window.__peaSetZoom(2.0); }")
        page.wait_for_timeout(500)
        page.mouse.move(a_box["x"] + a_box["width"] / 2, a_box["y"] + a_box["height"] / 2)
        page.wait_for_timeout(300)
        page.mouse.move(a_box["x"] + a_box["width"] - 10, a_box["y"] + a_box["height"] / 2, steps=4)
        page.wait_for_timeout(200)
        m2 = measure("right")
        inside2 = m2["handleLeft"] < m2["nodeRight"]
        results.append({"zoom": 2.0, "push_in": 10, "measure": m2, "handle_inside_box": inside2})

        out = {"results": results}
        # 断言：任何 push 下手柄都不进入框
        all_bounce = all(not r["handle_inside_box"] for r in results)
        out["all_bounced_back"] = all_bounce
        out["handle_w_zoom1"] = results[0]["measure"]["handleW"]
        out["handle_w_zoom2"] = m2["handleW"]
        print(json.dumps(out, indent=2, ensure_ascii=False))
        print("\nRESULT:", "ALL PASS" if all_bounce else "FAIL")
        b.close()
        import sys
        sys.exit(0 if all_bounce else 1)

if __name__ == "__main__":
    main()
