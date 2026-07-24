'''证据驱动：把节点放到低处/平移到边缘，用 elementFromPoint 真命中测试是否被裁切。'''
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

JS_HIT = r'''
(sel) => {
  const nodes = Array.from(document.querySelectorAll('.react-flow__node'));
  return nodes.map(n => {
    const r = n.getBoundingClientRect();
    const pts = [
      [r.left+r.width/2, r.top+8],
      [r.left+r.width/2, r.bottom-8],
      [r.left+8, r.top+r.height/2],
      [r.right-8, r.top+r.height/2],
    ];
    const hits = pts.map(([x,y]) => { const h=document.elementFromPoint(x,y); return !!(h && n.contains(h)); });
    return { id:n.getAttribute('data-id'), rect:{x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height)}, hits, anyVisible: hits.some(Boolean) };
  });
}
'''

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"clip_{ts}@pea.dev")
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
        # 节点放到靠近底部（y=820）和中间
        add_at("文本", 360, 820)
        add_at("图片", 1000, 820)
        page.wait_for_timeout(800)

        print("=== 低处节点（接近底部 900）命中测试 ===")
        for d in page.evaluate(JS_HIT):
            print(f"  node {d['id']} rect={d['rect']} hits={d['hits']} anyVisible={d['anyVisible']}")

        # 平移画布：把 viewport 向上移，使底部节点移出顶部 → 模拟用户平移后连线看不到
        print("\n=== 平移 viewport 使节点上移出屏后命中测试 ===")
        page.evaluate("""() => {
          const rf = document.querySelector('.react-flow');
          // 通过 React Flow 的内部 store 设置 viewport（平移 y 到 -600）
          const inst = rf && rf.__rf$? null : null;
        }""")
        # 用屏幕平移：拖拽 pane 平移
        page.mouse.move(700, 450)
        page.mouse.down()
        page.mouse.move(700, 120, steps=10)
        page.mouse.up()
        page.wait_for_timeout(400)
        vp = page.evaluate("() => { const vp=document.querySelector('.react-flow__viewport'); return vp? getComputedStyle(vp).transform : null; }")
        print("  平移后 viewport transform:", vp)
        for d in page.evaluate(JS_HIT):
            print(f"  node {d['id']} rect={d['rect']} hits={d['hits']} anyVisible={d['anyVisible']}")
        page.screenshot(path=str(SHOTS/"diag_panned.png"))

        b.close()

if __name__ == "__main__":
    main()
