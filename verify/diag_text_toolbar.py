"""诊断：文本节点工具栏 第一点击有、第二点击没 的复现。
复现多种交互序列，打印 selectedIds 与 .text-node-toolbar 可见性。
"""
import os, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)

def log(*a):
    print("[diag_text]", *a, flush=True)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        pg = ctx.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append("PAGEERR:" + str(e)))
        pg.goto(BASE, wait_until="networkidle")
        pg.wait_for_timeout(400)

        # 注册/登录
        try:
            pg.click("text=去注册", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(300)
        pg.fill("input:visible >> nth=0", "tcheck_%d@pea.ai" % int(__import__("time").time()))
        pg.fill("input:visible >> nth=1", "Passw0rd!")
        try:
            pg.click("button:has-text('注')", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(800)
        # 新建项目
        try:
            pg.click("text=新建项目", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(900)

        # 进画布：点第一个项目卡片
        try:
            pg.click(".projects-card", timeout=6000)
        except Exception:
            pass
        pg.wait_for_timeout(1200)

        def state():
            return pg.evaluate("window.__canvas ? window.__canvas.getState().selectedIds : 'NO_HOOK'")

        def toolbar_info():
            return pg.evaluate("""() => {
              const t = document.querySelector('.text-node-toolbar');
              if (!t) return {exists:false};
              const r = t.getBoundingClientRect();
              const cs = getComputedStyle(t);
              return {exists:true, vis: cs.visibility, op: cs.opacity, disp: cs.display,
                      w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top)};
            }""")

        # 添加文本节点
        pg.click(".pea-tlb-btn[aria-label*='添加节点']", timeout=5000)
        pg.wait_for_timeout(300)
        pg.click(".pea-add-menu-item:has-text('文本')", timeout=5000)
        pg.wait_for_timeout(900)

        # 找到刚加的文本节点并点击
        node = pg.locator(".react-flow__node").last
        node.scroll_into_view_if_needed()
        pg.wait_for_timeout(300)

        def click_node(label):
            box = node.bounding_box()
            cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
            pg.mouse.click(cx, cy)
            pg.wait_for_timeout(500)
            log(f"{label}: selectedIds={state()} toolbar={toolbar_info()}")

        log("=== 序列A：连续两次单击同一节点 ===")
        click_node("第1击")
        pg.screenshot(path=os.path.join(SHOTS, "diag_text_a1.png"))
        click_node("第2击")
        pg.screenshot(path=os.path.join(SHOTS, "diag_text_a2.png"))

        log("=== 序列B：点节点→点空白→再点节点（重新选中）===")
        # 点空白 pane
        pg.mouse.click(200, 700)
        pg.wait_for_timeout(400)
        log(f"点空白后 selectedIds={state()} toolbar={toolbar_info()}")
        click_node("重新点节点")
        # 轮询 2s 看工具栏是否恢复
        for i in range(10):
            pg.wait_for_timeout(200)
            t = toolbar_info()
            if t["exists"]:
                log(f"  轮询{i*200}ms 工具栏恢复: {t}")
                break
        else:
            log("  轮询2s 工具栏仍未恢复 (永久消失)")

        log("=== 序列C：双击节点（进编辑）后再看工具栏 ===")
        box = node.bounding_box()
        cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
        pg.mouse.dblclick(cx, cy)
        pg.wait_for_timeout(500)
        log(f"双击后 selectedIds={state()} editing? toolbar={toolbar_info()}")
        pg.screenshot(path=os.path.join(SHOTS, "diag_text_c.png"))

        log("CONSOLE_ERRORS:", errs[:5])
        b.close()

if __name__ == "__main__":
    main()
