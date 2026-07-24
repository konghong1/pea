'''真实验证（修正假阳性）：
- 用 document.elementFromPoint 在节点中心做命中测试（遵守 overflow 裁切），
  只有返回节点内部元素才说明节点真的可见。
- 输出每个节点的祖先裁剪链（找出 overflow:hidden 的祖先）。
- 静止态 vs 连线中 分别做命中测试，定位连线时看不到的真因。
- 最后测试连线后能否删除。
'''
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

JS_ANALYZE = r'''
() => {
  const nodes = Array.from(document.querySelectorAll('.react-flow__node'));
  return nodes.map(n => {
    const r = n.getBoundingClientRect();
    const cx = r.left + r.width/2, cy = r.top + r.height/2;
    const hit = document.elementFromPoint(cx, cy);
    const hitInside = !!(hit && n.contains(hit));
    const chain = [];
    let el = n.parentElement;
    while (el && el !== document.body) {
      const cs = getComputedStyle(el);
      const er = el.getBoundingClientRect();
      const clipped = (cs.overflow === 'hidden' || cs.overflowX === 'hidden' || cs.overflowY === 'hidden')
        && (r.left < er.left || r.top < er.top || r.right > er.right || r.bottom > er.bottom);
      chain.push({ tag: el.tagName, cls: (el.className||'').toString().slice(0,40), ov: cs.overflow, clipped });
      el = el.parentElement;
    }
    return { id: n.getAttribute('data-id'),
      rect: {x:Math.round(r.left), y:Math.round(r.top), w:Math.round(r.width), h:Math.round(r.height)},
      center: {x:Math.round(cx), y:Math.round(cy)},
      hitTag: hit ? hit.tagName + '.' + ((hit.className||'').toString().slice(0,30)) : null,
      hitInside, chain };
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
        page.fill('input[placeholder="you@pea.ai"]', f"diag_{ts}@pea.dev")
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

        analyze = lambda: page.evaluate(JS_ANALYZE)

        print("=== 静止态：祖先裁剪链 + 命中测试 ===")
        data = analyze()
        for d in data:
            print(f"node {d['id']} rect={d['rect']} center=({d['center']['x']},{d['center']['y']}) hitInside={d['hitInside']} hit={d['hitTag']}")
            for c in d['chain']:
                flag = " <<CLIP" if c['clipped'] else ""
                print(f"    ancestor {c['tag']}.{c['cls']} overflow={c['ov']}{flag}")

        print("\n=== 连线中：命中测试 ===")
        nodes = page.locator(".react-flow__node")
        src = nodes.nth(0).locator(".react-flow__handle.source").first
        hb = src.bounding_box()
        hx, hy = hb["x"]+hb["width"]/2, hb["y"]+hb["height"]/2
        img = nodes.nth(1).bounding_box()
        page.mouse.move(hx, hy)
        page.mouse.down()
        page.wait_for_timeout(120)
        page.mouse.move((hx+img["x"]+img["width"]/2)/2, (hy+img["y"]+img["height"]/2)/2, steps=6)
        page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS/"diag_connecting.png"))
        connState = page.evaluate("() => ({ rfConnecting: document.querySelector('.react-flow').classList.contains('connecting'), paneConnecting: document.querySelector('.react-flow__pane') && document.querySelector('.react-flow__pane').classList.contains('connecting'), hasConnectingClass: !!document.querySelector('.react-flow__connecting') })")
        print("连线态 class:", connState)
        data_c = analyze()
        for d in data_c:
            print(f"  [连线中] node {d['id']} hitInside={d['hitInside']} hit={d['hitTag']}")
        page.mouse.move(img["x"]+img["width"]/2, img["y"]+img["height"]/2, steps=6)
        page.wait_for_timeout(150)
        page.mouse.up()
        page.wait_for_timeout(500)
        edges = page.locator(".react-flow__edge").count()
        print(f"\n连线后 边数量: {edges}")
        page.screenshot(path=str(SHOTS/"diag_edge.png"))

        if edges > 0:
            eb = page.locator(".react-flow__edge").first.bounding_box()
            ex, ey = eb["x"]+eb["width"]/2, eb["y"]+eb["height"]/2
            page.mouse.click(ex, ey)
            page.wait_for_timeout(300)
            sel = page.evaluate("() => document.querySelectorAll('.react-flow__edge.selected').length")
            print(f"  点击边后 选中边数: {sel}")
            page.keyboard.press("Delete")
            page.wait_for_timeout(400)
            edges2 = page.locator(".react-flow__edge").count()
            print(f"  按 Delete 后 边数量: {edges2} (期望 0)")
            page.screenshot(path=str(SHOTS/"diag_after_delete.png"))

        b.close()

if __name__ == "__main__":
    main()
