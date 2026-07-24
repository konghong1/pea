'''深度诊断：连线时文本节点为何在视觉上消失。
在同一帧内同时采集：
1. 全页截图
2. 每个节点的完整祖先链 overflow/display/opacity/transform/z-index
3. 节点实际 DOM 是否存在、bounding box、是否在视口内
4. react-flow viewport 当前变换矩阵
5. 是否有全屏遮罩层覆盖节点区域
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
            page.fill('input[placeholder="you@pea.ai"]', f"diag_{ts}@pea.dev")
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

        # 截图：正常状态
        page.screenshot(path=str(SHOTS / "diag_deep_00_idle.png"))

        nodes = page.locator(".react-flow__node")

        # 选中文本节点（触发输入框）
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

        # === 同一帧内采集所有数据 ===
        diag = page.evaluate("""() => {
          const vp = document.querySelector('.react-flow__viewport');
          const vpStyle = vp ? getComputedStyle(vp) : null;
          const vpTransform = vpStyle ? vpStyle.transform : 'none';
          const rf = document.querySelector('.react-flow');
          const rfClass = rf ? rf.className : '';

          // 收集所有 .react-flow__node 的完整信息
          const nodeInfos = Array.from(document.querySelectorAll('.react-flow__node')).map((n, i) => {
            const r = n.getBoundingClientRect();
            const cs = getComputedStyle(n);
            // 祖先链 overflow
            let el = n.parentElement;
            const ancestors = [];
            while (el && el !== document.body) {
              const s = getComputedStyle(el);
              ancestors.push({
                tag: el.tagName,
                cls: el.className?.toString?.()?.slice?.(0, 80) || '',
                overflow: s.overflow,
                overflowX: s.overflowX,
                overflowY: s.overflowY,
                display: s.display,
                opacity: s.opacity,
                visibility: s.visibility,
                zIndex: s.zIndex,
                position: s.position,
                transform: s.transform,
              });
              el = el.parentElement;
            }
            // 节点中心 elementFromPoint
            const cx = r.left + r.width/2, cy = r.top + r.height/2;
            const hit = document.elementFromPoint(cx, cy);
            // 节点左上角 elementFromPoint
            const hitTL = document.elementFromPoint(r.left+5, r.top+5);
            return {
              idx: i,
              id: n.getAttribute('data-id'),
              kind: n.querySelector('.pea-node')?.getAttribute('data-kind'),
              rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
              style: { display: cs.display, opacity: cs.opacity, visibility: cs.visibility, zIndex: cs.zIndex, transform: cs.transform, pointerEvents: cs.pointerEvents },
              centerHit: hit ? { tag: hit.tagName, cls: hit.className?.toString?.()?.slice?.(0, 80) || '', id: hit.id } : null,
              centerHitInsideNode: !!(hit && n.contains(hit)),
              tlHit: hitTL ? { tag: hitTL.tagName, cls: hitTL.className?.toString?.()?.slice?.(0, 80) || '' } : null,
              tlHitInsideNode: !!(hitTL && n.contains(hitTL)),
              inViewport: r.bottom > 0 && r.right > 0 && r.top < window.innerHeight && r.left < window.innerWidth,
              ancestorCount: ancestors.length,
              ancestors: ancestors.slice(0, 12),
            };
          });

          // 检查是否有 fixed 定位的全屏遮罩
          const overlays = Array.from(document.querySelectorAll('*')).filter(el => {
            const s = getComputedStyle(el);
            return (s.position === 'fixed' || s.position === 'absolute') &&
                   parseInt(s.zIndex) > 5 &&
                   el.getBoundingClientRect().width > window.innerWidth * 0.3;
          }).map(el => ({
            tag: el.tagName, cls: el.className?.toString?.()?.slice?.(0, 100) || '',
            rect: (() => { const r = el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
            zIndex: getComputedStyle(el).zIndex,
          }));

          return {
            reactFlowClass: rfClass,
            viewportTransform: vpTransform,
            windowSize: { w: window.innerWidth, h: window.innerHeight },
            nodes: nodeInfos,
            overlays: overlays.slice(0, 15),
          };
        }""")

        # 截图：连线中（与上述数据同一时刻）
        page.screenshot(path=str(SHOTS / "diag_deep_01_connecting.png"))

        # 打印完整诊断
        import json
        print("=== 连线中深度诊断 ===")
        print(f"react-flow class: {diag['reactFlowClass']}")
        print(f"viewport transform: {diag['viewportTransform']}")
        print(f"window: {diag['windowSize']}")
        for n in diag["nodes"]:
            print(f"\n--- node[{n['idx']}] id={n['id']} kind={n['kind']} ---")
            print(f"  rect={n['rect']} inViewport={n['inViewport']}")
            print(f"  style: d={n['style']['display']} o={n['style']['opacity']} v={n['style']['visibility']} pe={n['style']['pointerEvents']} z={n['style']['zIndex']}")
            print(f"  centerHit: tag={n['centerHit']['tag'] if n['centerHit'] else None} cls={(n['centerHit']['cls'] or '')[:60] if n['centerHit'] else None} insideNode={n['centerHitInsideNode']}")
            print(f"  tlHit:    tag={n['tlHit']['tag'] if n['tlHit'] else None} cls={(n['tlHit']['cls'] or '')[:60] if n['tlHit'] else None} insideNode={n['tlHitInsideNode']}")
            print(f"  ancestor chain ({n['ancestorCount']} levels):")
            for a in n["ancestors"][:8]:
                print(f"    <{a['tag']}> .{str(a['cls'])[:50]} of={a['overflow']} d={a['display']} op={a['opacity']} z={a['zIndex']} pos={a['position']} tf={a['transform'][:40]}")

        print(f"\n=== 大面积遮罩层 (z>5, w>30%vw) ===")
        for o in diag["overlays"]:
            print(f"  <{o['tag']}> .{str(o['cls'])[:80]} rect={o['rect']} z={o['zIndex']}")

        # 释放鼠标
        page.mouse.move(tb["x"]+tb["width"]/2, tb["y"]+tb["height"]/2, steps=6)
        page.wait_for_timeout(200)
        page.mouse.up()
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOTS / "diag_deep_02_after.png"))
        print(f"\nedges: {page.locator('.react-flow__edge').count()}")
        print(f"errors: {errors[:10]}")
        b.close()

if __name__ == "__main__":
    main()
