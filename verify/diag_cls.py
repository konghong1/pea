'''诊断：ReactFlow v11 连线期间 DOM 状态（类名、SVG 元素、节点可见性）。
'''
import time
from playwright.sync_api import sync_playwright
from pathlib import Path

SHOTS = Path("C:/workspace/pea/verify/shots")

def main():
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
            page.fill('input[placeholder="you@pea.ai"]', f"cls_{ts}@pea.dev")
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
        add_at("文本", 420, 340)
        add_at("图片", 980, 340)
        page.wait_for_timeout(900)

        # 正常状态快照
        idle_info = page.evaluate("""() => {
          const rf = document.querySelector('.react-flow');
          return {
            rfClasses: rf?.className,
            rfChildClasses: Array.from(rf?.children || []).map(c => ({tag:c.tagName, cls:c.className})),
            svgs: Array.from(document.querySelectorAll('.react-flow svg')).map(s => ({
              cls: s.className?.baseVal || s.getAttribute('class') || '',
              id: s.id,
              rect: (() => { const r=s.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
              zIndex: getComputedStyle(s).zIndex,
              childCount: s.children.length,
              firstChildTag: s.children[0]?.tagName,
            })),
          };
        }""")
        print("=== IDLE state ===")
        print(f"  .react-flow classes: {idle_info['rfClasses']}")
        for c in idle_info['rfChildClasses']:
            print(f"  child: <{c['tag']}> .{c['cls']}")
        for s in idle_info['svgs']:
            print(f"  svg: class='{s['cls']}' id={s['id']} rect={s['rect']} z={s['zIndex']} children={s['childCount']} first=<{s['firstChildTag']}>")

        nodes = page.locator(".react-flow__node")

        # 选中文本节点 → 触发输入框
        nb0 = nodes.nth(0).bounding_box()
        page.mouse.click(nb0["x"]+nb0["width"]/2, nb0["y"]+nb0["height"]/2)
        page.wait_for_timeout(400)

        # 获取 source 手柄位置
        src = nodes.nth(0).locator(".react-flow__handle.source").first.bounding_box()
        hx, hy = src["x"]+src["width"]/2, src["y"]+src["height"]/2
        tb = nodes.nth(1).bounding_box()

        # 发起连线拖拽 → 移动到中点
        page.mouse.move(hx, hy)
        page.mouse.down()
        page.wait_for_timeout(200)
        midx, midy = (hx+tb["x"]+tb["width"]/2)/2, (hy+tb["y"]+tb["height"]/2)/2
        page.mouse.move(midx, midy, steps=10)
        page.wait_for_timeout(300)

        # === 连线中完整 DOM 快照 ===
        conn_info = page.evaluate("""() => {
          const rf = document.querySelector('.react-flow');
          // 收集所有带 'connect' 关键字的类名
          const allEls = document.querySelectorAll('*');
          const connClasses = [];
          for (const el of allEls) {
            const cls = el.className;
            if (typeof cls === 'string' && /connect/i.test(cls)) {
              connClasses.push({
                tag: el.tagName,
                cls: cls.slice(0, 120),
                id: el.id,
                rect: (() => { const r=el.getBoundingClientRect(); return r.width>0 ? {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)} : null; })(),
              });
            }
          }
          // 所有 SVG 详情
          const svgs = Array.from(document.querySelectorAll('svg')).map(s => ({
            cls: s.getAttribute('class') || s.className?.baseVal || '',
            id: s.id,
            parentCls: s.parentElement?.className?.toString?.()?.slice(0,80) || '',
            rect: (() => { const r=s.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
            zIndex: getComputedStyle(s).zIndex,
            fill: s.getAttribute('fill'),
            bg: getComputedStyle(s).background,
            pointerEvents: getComputedStyle(s).pointerEvents,
          }));
          // 文本节点的完整 outerHTML 片段（前500字符）
          const n0 = document.querySelectorAll('.react-flow__node')[0];
          return {
            rfClasses: rf?.className,
            connectElements: connClasses,
            svgs: svgs,
            node0_outerSnippet: n0?.outerHTML?.slice(0, 600),
            node0_computed: n0 ? {
              display: getComputedStyle(n0).display,
              opacity: getComputedStyle(n0).opacity,
              visibility: getComputedStyle(n0).visibility,
              zIndex: getComputedStyle(n0).zIndex,
              transform: getComputedStyle(n0).transform,
              clipPath: getComputedStyle(n0).clipPath,
              clip: getComputedStyle(n0).clip,
              overflow: getComputedStyle(n0).overflow,
              position: getComputedStyle(n0).position,
            } : null,
          };
        }""")

        page.screenshot(path=str(SHOTS / "diag_cls_01_connecting.png"))

        print("\n=== CONNECTING state ===")
        print(f"  .react-flow classes: {conn_info['rfClasses']}")
        print(f"\n  带 'connect' 关键字的元素 ({len(conn_info['connectElements'])}):")
        for e in conn_info['connectElements']:
            print(f"    <{e['tag']}> .{e['cls']} id={e['id']} rect={e['rect']}")
        print(f"\n  所有 SVG ({len(conn_info['svgs'])}):")
        for s in conn_info['svgs']:
            print(f"    class='{s['cls']}' parent=.{s['parentCls']} rect={s['rect']} z={s['zIndex']} fill={s['fill']} bg={s['bg']} pe={s['pointerEvents']}")
        print(f"\n  node[0] computed:")
        for k, v in (conn_info['node0_computed'] or {}).items():
            print(f"    {k}: {v}")
        print(f"\n  node[0] HTML snippet:\n{conn_info['node0_outerSnippet'][:400]}")

        # 释放
        page.mouse.move(tb["x"]+tb["width"]/2, tb["y"]+tb["height"]/2, steps=6)
        page.wait_for_timeout(200)
        page.mouse.up()
        page.wait_for_timeout(500)
        edges = page.locator(".react-flow__edge").count()
        print(f"\nedges: {edges}  errors: {errors[:5]}")
        b.close()

if __name__ == "__main__":
    main()
