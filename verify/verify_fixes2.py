'''忠实验证（针对用户反馈的两点）：
A. 节点在连线/低处不被裁切 —— 断言画布外框 overflow==visible（根因已移除），
   并对低处节点做 elementFromPoint 真命中测试（底边在窗口内时不再被容器裁掉）。
B. 连线可删除 —— 选中边后出现 .pea-edge-del 按钮，点击即删；键盘 Delete 亦可用。
同时回归：连线建边、连线中节点可见。
硬标准：0 console error。
'''
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
errors = []

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"fx2_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "D")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        add_at = lambda label, x, y: (
            page.mouse.dblclick(x, y) or page.wait_for_timeout(350)
            or page.locator(".pea-add-menu-item", has_text=label).first.click()
            or page.wait_for_timeout(600)
        )
        add_at("文本", 360, 300)
        add_at("图片", 1000, 300)
        page.wait_for_timeout(800)

        # ---- A1: 根因移除断言 ----
        print("=== A. 裁切根因 ===")
        ov = page.evaluate("""() => Array.from(document.querySelectorAll('.relative.flex-1')).map(e=>getComputedStyle(e).overflow)""")
        print(f"  画布外框 .relative.flex-1 overflow = {ov}")
        assert "visible" in ov, f"画布外框仍裁切: {ov}"

        # ---- A2: 低处节点不被容器裁切（拖到接近底部，底边落在窗口内、原容器边界外）----
        print("\n=== A2. 低处节点真命中测试 ===")
        nodes = page.locator(".react-flow__node")
        # 拖动 image 节点向下 ~400px，使其底边进入窗口下半部
        ib = nodes.nth(1).bounding_box()
        sx, sy = ib["x"]+ib["width"]/2, ib["y"]+ib["height"]/2
        page.mouse.move(sx, sy); page.mouse.down()
        page.mouse.move(sx, sy+400, steps=12); page.mouse.up()
        page.wait_for_timeout(400)
        low = page.evaluate("""() => {
          const n = document.querySelectorAll('.react-flow__node')[1];
          const r = n.getBoundingClientRect();
          const bottomHit = document.elementFromPoint(r.left+r.width/2, r.bottom-12);
          return { rect:{y:Math.round(r.top), bottom:Math.round(r.bottom)}, bottomHitInside: !!(bottomHit && n.contains(bottomHit)) };
        }""")
        print(f"  低处节点 rect={low['rect']} 底边命中(窗口内,应True)={low['bottomHitInside']}")
        assert low["bottomHitInside"], f"低处节点底边仍被裁切: {low}"
        page.screenshot(path=str(SHOTS/"fx2_low_node.png"))

        # ---- 连线建边 + 连线中节点可见（回归）----
        print("\n=== 连线建边 + 连线中可见 ===")
        click_node = lambda i: (nodes.nth(i).bounding_box() and page.mouse.click(
            nodes.nth(i).bounding_box()["x"]+nodes.nth(i).bounding_box()["width"]/2,
            nodes.nth(i).bounding_box()["y"]+nodes.nth(i).bounding_box()["height"]*0.6))
        click_node(0); page.wait_for_timeout(300)
        src = nodes.nth(0).locator(".react-flow__handle.source").first.bounding_box()
        hx, hy = src["x"]+src["width"]/2, src["y"]+src["height"]/2
        tb = nodes.nth(1).bounding_box()
        page.mouse.move(hx, hy); page.mouse.down(); page.wait_for_timeout(120)
        page.mouse.move((hx+tb["x"]+tb["width"]/2)/2, (hy+tb["y"]+tb["height"]/2)/2, steps=6)
        page.wait_for_timeout(150)
        vis = page.evaluate("""() => Array.from(document.querySelectorAll('.react-flow__node')).map(n=>{
          const r=n.getBoundingClientRect(); const h=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
          return !!(h && n.contains(h)); })""")
        print(f"  连线中节点可见: {vis}")
        assert all(vis), f"连线中节点不可见: {vis}"
        page.mouse.move(tb["x"]+tb["width"]/2, tb["y"]+tb["height"]/2, steps=6)
        page.wait_for_timeout(150); page.mouse.up(); page.wait_for_timeout(500)
        edges = page.locator(".react-flow__edge").count()
        print(f"  边数量: {edges}")
        assert edges >= 1, "连线未建边"
        page.screenshot(path=str(SHOTS/"fx2_edge.png"))

        # ---- B1: 删除按钮（可见、可点）----
        print("\n=== B1. 选中边 → 点 .pea-edge-del 删除 ===")
        eb = page.locator(".react-flow__edge").first.bounding_box()
        page.mouse.click(eb["x"]+eb["width"]/2, eb["y"]+eb["height"]/2)
        page.wait_for_timeout(300)
        del_btn = page.locator(".pea-edge-del")
        print(f"  删除按钮可见: {del_btn.count()>0 and del_btn.is_visible()}")
        assert del_btn.count() > 0 and del_btn.is_visible(), "选中边后未出现删除按钮"
        del_btn.click()
        page.wait_for_timeout(400)
        edges_after = page.locator(".react-flow__edge").count()
        print(f"  点删除按钮后 边数量: {edges_after} (期望 0)")
        assert edges_after == 0, f"删除按钮未删掉边: {edges_after}"
        page.screenshot(path=str(SHOTS/"fx2_after_del_btn.png"))

        # ---- B2: 键盘 Delete（防御）----
        print("\n=== B2. 再建边 → 键盘 Delete 删除 ===")
        click_node(0); page.wait_for_timeout(200)
        src = nodes.nth(0).locator(".react-flow__handle.source").first.bounding_box()
        hx, hy = src["x"]+src["width"]/2, src["y"]+src["height"]/2
        tb = nodes.nth(1).bounding_box()
        page.mouse.move(hx, hy); page.mouse.down(); page.wait_for_timeout(120)
        page.mouse.move(tb["x"]+tb["width"]/2, tb["y"]+tb["height"]/2, steps=8)
        page.wait_for_timeout(150); page.mouse.up(); page.wait_for_timeout(500)
        assert page.locator(".react-flow__edge").count() >= 1
        eb = page.locator(".react-flow__edge").first.bounding_box()
        page.mouse.click(eb["x"]+eb["width"]/2, eb["y"]+eb["height"]/2)
        page.wait_for_timeout(200)
        page.keyboard.press("Delete")
        page.wait_for_timeout(400)
        print(f"  键盘 Delete 后 边数量: {page.locator('.react-flow__edge').count()} (期望 0)")
        assert page.locator(".react-flow__edge").count() == 0

        print("\n=== 控制台错误 ===")
        for e in errors[:20]: print("  ", e)
        assert len(errors) == 0, f"存在控制台错误: {errors}"

        b.close()
        print("\n✅ 全部通过")

if __name__ == "__main__":
    main()
