"""验证：进入画布后，Ctrl/⌘ + 滚轮应缩放画布，而非触发浏览器整页缩放。

检查点：
1. Ctrl+wheel 事件被画布容器拦截 (defaultPrevented === true) -> 浏览器整页缩放被阻止。
2. 真实 Ctrl+wheel 使 ReactFlow 视口 zoom 增大 -> 画布确实在缩放。
3. 普通滚轮不改变 zoom -> panOnScroll 平移手势未被破坏。

用法：python verify_ctrl_wheel_zoom.py
"""
import os, sys, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

def log(*a):
    print("[verify_ctrl_wheel]", *a, flush=True)

def get_zoom(pg):
    return pg.evaluate("""() => {
      const vp = document.querySelector('.react-flow__viewport');
      if (!vp) return null;
      const t = vp.style.transform || getComputedStyle(vp).transform;
      const m = t.match(/scale\\(([0-9.]+)\\)/);
      if (m) return parseFloat(m[1]);
      // 退化：从 matrix 解析
      const mm = t.match(/matrix\\(([^)]+)\\)/);
      if (mm) { const p = mm[1].split(',').map(parseFloat); return p[0]; }
      return null;
    }""")

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        # 同时设置 window 与 localStorage.__peaDevHooks，确保生产构建暴露 __canvas
        ctx.add_init_script("window.__peaDevHooks='1'; try{localStorage.setItem('__peaDevHooks','1')}catch(e){}")
        pg = ctx.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append("PAGEERR:" + str(e)))

        pg.goto(BASE, wait_until="domcontentloaded")
        pg.wait_for_timeout(600)

        # 注册 / 登录
        try:
            pg.click("text=去注册", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(300)
        try:
            pg.fill("input:visible >> nth=0", "wz%d@pea.ai" % int(time.time()))
            pg.fill("input:visible >> nth=1", "Passw0rd!")
            pg.click("button:has-text('注')", timeout=4000)
        except Exception as e:
            log("register step skipped/err:", e)
        pg.wait_for_timeout(900)

        # 新建项目 -> 进画布
        try:
            pg.click("text=新建项目", timeout=6000)
        except Exception as e:
            log("新建项目 click err:", e)
        pg.wait_for_timeout(1500)

        # 等待画布 store 与 ReactFlow viewport 就绪
        pg.wait_for_selector(".react-flow__viewport", timeout=8000)
        canvas_ok = pg.evaluate("typeof window.__canvas !== 'undefined' && window.__canvas.getState().canvasId != null")
        log("canvas ready (store+id):", canvas_ok)
        if not canvas_ok:
            log("WARN: 画布未就绪，尝试通过 UI 直接进入")
        pg.wait_for_timeout(500)

        # 让画布获得焦点区域；取画布中心作为滚轮落点
        box = pg.evaluate("""() => {
          const r = document.querySelector('.react-flow__pane') || document.querySelector('.react-flow__renderer');
          const b = r.getBoundingClientRect();
          return { x: b.x + b.width/2, y: b.y + b.height/2 };
        }""")
        cx, cy = box["x"], box["y"]
        log("pane center:", cx, cy)

        # 检查点 1：Ctrl+wheel 是否被画布拦截 (defaultPrevented)
        prevented = pg.evaluate("""() => {
          const pane = document.querySelector('.react-flow__pane') || document.querySelector('.pea-canvas-flow');
          const ev = new WheelEvent('wheel', { bubbles: true, cancelable: true, ctrlKey: true, deltaY: -120 });
          pane.dispatchEvent(ev);
          return ev.defaultPrevented;
        }""")
        log("检查点1 Ctrl+wheel defaultPrevented (应 True):", prevented)

        # 基线 zoom
        z0 = get_zoom(pg)
        log("基线 zoom:", z0)

        # 检查点 2：真实 Ctrl+wheel 缩放画布 (向上滚 = 放大)
        pg.mouse.move(cx, cy)
        pg.keyboard.down("Control")
        pg.mouse.wheel(0, -360)
        pg.keyboard.up("Control")
        pg.wait_for_timeout(400)
        z1 = get_zoom(pg)
        log("Ctrl+wheel 后 zoom:", z1)

        # 再放大多一次，确认单调增大
        pg.mouse.move(cx, cy)
        pg.keyboard.down("Control")
        pg.mouse.wheel(0, -360)
        pg.keyboard.up("Control")
        pg.wait_for_timeout(400)
        z2 = get_zoom(pg)
        log("第二次 Ctrl+wheel 后 zoom:", z2)

        # 检查点 3：普通滚轮不改变 zoom (应保持平移)
        z3 = get_zoom(pg)
        pg.mouse.move(cx, cy)
        pg.mouse.wheel(0, 400)
        pg.wait_for_timeout(400)
        z4 = get_zoom(pg)
        log("普通滚轮前 zoom:", z3, " 后 zoom:", z4)

        # 判定
        ok1 = prevented is True
        ok2 = (z0 is not None) and (z1 is not None) and (z2 is not None) and (z1 > z0 + 1e-3) and (z2 > z1 + 1e-3)
        ok3 = (z3 is not None) and (z4 is not None) and abs(z4 - z3) < 1e-3

        log("--------------------------------------------------")
        log("结果汇总:")
        log("  [1] Ctrl+wheel 被拦截(defaultPrevented) :", ok1)
        log("  [2] Ctrl+wheel 画布放大 (zoom↑)         :", ok2, f"({z0} -> {z1} -> {z2})")
        log("  [3] 普通滚轮不缩放(panOnScroll 保持)    :", ok3, f"({z3} -> {z4})")
        log("  console errors:", len(errs))
        for e in errs[:6]:
            log("    ERR:", e)
        passed = ok1 and ok2 and ok3
        log("=> 总体:", "PASS ✅" if passed else "FAIL ❌")
        b.close()
        sys.exit(0 if passed else 1)

if __name__ == "__main__":
    main()
