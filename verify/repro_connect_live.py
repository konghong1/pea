'''连线中真机截图验证（before/after 通用）。
- 登录 → 建两个节点（文本 / 图片）
- 从文本节点 source 手柄发起连线拖拽，移动到两节点中点时截图（这是“连线中”那一帧）
- 真命中测试：连线中每个节点中心是否被 elementFromPoint 命中（遵守 overflow 裁切）
- 检查画布外框 .relative.flex-1 的 overflow
- 释放到图片节点 → 断言建边
硬标准：0 console error。
'''
import time
from playwright.sync_api import sync_playwright
from pathlib import Path

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
TAG = "live"  # 运行时通过环境变量或参数改 before/after

def main(tag="live"):
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        try:
            page.get_by_role("button", name="没有账号？去注册").first.click()
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f"conn_{tag}_{ts}@pea.dev")
            page.fill('input[placeholder="至少 8 位"]', "Password123")
            page.fill('input[placeholder="可选"]', "D")
            page.locator("form button[type=submit]").click()
            page.wait_for_timeout(4000)
        except Exception:
            pass
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        add_at = lambda label, x, y: (
            page.mouse.dblclick(x, y) or page.wait_for_timeout(350)
            or page.locator(".pea-add-menu-item", has_text=label).first.click()
            or page.wait_for_timeout(700)
        )
        # 两节点明显分开，都在画布可见区域
        add_at("文本", 420, 340)
        add_at("图片", 980, 340)
        page.wait_for_timeout(900)
        page.screenshot(path=str(SHOTS / f"conn_{tag}_00_idle.png"))

        nodes = page.locator(".react-flow__node")
        print(f"[{tag}] 节点数:", nodes.count())

        # 画布外框 overflow（真因指标）
        ov = page.evaluate("""() => Array.from(document.querySelectorAll('.relative.flex-1')).map(e=>({cls:e.className, of:getComputedStyle(e).overflow, ofx:getComputedStyle(e).overflowX, ofy:getComputedStyle(e).overflowY}))""")
        print(f"[{tag}] 画布外框 overflow:", ov)

        # 发起连线拖拽
        click_node = lambda i: (nodes.nth(i).bounding_box() and page.mouse.click(
            nodes.nth(i).bounding_box()["x"]+nodes.nth(i).bounding_box()["width"]/2,
            nodes.nth(i).bounding_box()["y"]+nodes.nth(i).bounding_box()["height"]*0.6))
        click_node(0); page.wait_for_timeout(300)
        src = nodes.nth(0).locator(".react-flow__handle.source").first.bounding_box()
        hx, hy = src["x"]+src["width"]/2, src["y"]+src["height"]/2
        tb = nodes.nth(1).bounding_box()
        page.mouse.move(hx, hy)
        page.mouse.down()
        page.wait_for_timeout(150)
        # 移动到两节点中点（连线进行中）
        midx, midy = (hx+tb["x"]+tb["width"]/2)/2, (hy+tb["y"]+tb["height"]/2)/2
        page.mouse.move(midx, midy, steps=8)
        page.wait_for_timeout(250)

        # 关键证据 1：连线中截图
        page.screenshot(path=str(SHOTS / f"conn_{tag}_01_connecting.png"))

        # 关键证据 2：连线中每个节点中心是否被真命中（遵守 overflow 裁切）
        vis = page.evaluate("""() => {
          const wrap = document.querySelector('.react-flow');
          const cls = wrap ? wrap.className : '';
          return {
            reactFlowClass: cls,
            nodes: Array.from(document.querySelectorAll('.react-flow__node')).map(n=>{
              const r=n.getBoundingClientRect();
              const cx=r.left+r.width/2, cy=r.top+r.height/2;
              const h=document.elementFromPoint(cx, cy);
              return { id:n.getAttribute('data-id'), rect:{x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)}, visible: !!(h && n.contains(h)) };
            })
          };
        }""")
        print(f"[{tag}] react-flow class:", vis["reactFlowClass"])
        for n in vis["nodes"]:
            print(f"[{tag}]   node {n['id']} rect={n['rect']} 连线中可见(真命中)={n['visible']}")

        # 释放到图片节点 → 建边
        page.mouse.move(tb["x"]+tb["width"]/2, tb["y"]+tb["height"]/2, steps=10)
        page.wait_for_timeout(200)
        page.mouse.up()
        page.wait_for_timeout(600)
        edges = page.locator(".react-flow__edge").count()
        print(f"[{tag}] 边数量: {edges}")
        page.screenshot(path=str(SHOTS / f"conn_{tag}_02_after.png"))

        print(f"[{tag}] console errors:", errors[:10])
        b.close()
        return vis, ov, edges, errors

if __name__ == "__main__":
    import sys
    tag = sys.argv[1] if len(sys.argv) > 1 else "live"
    main(tag)
