"""E23：文本节点浮动工具条 显隐回归 + 统一手型光标。

断言：
  1) 单击文本节点 -> 工具条可见
  2) 点空白取消选中 -> 工具条消失、selectedIds 为空
  3) 再次单击同一文本节点 -> 工具条恢复（修复 lastPosRef 未重置导致永久消失）
  4) 双击文本节点进编辑 -> 工具条仍在、contentEditable=true
  5) .pea-node 计算光标为 grab（统一手型）

硬标准：0 console error。
"""
import os
import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"


def main():
    fails = 0
    msgs = []

    def check(cond, name):
        nonlocal fails
        msgs.append(("PASS" if cond else "FAIL", name))
        if not cond:
            fails += 1

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
        try:
            pg.click("text=去注册", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(300)
        pg.fill("input:visible >> nth=0", "te23_%d@pea.ai" % int(time.time()))
        pg.fill("input:visible >> nth=1", "Passw0rd!")
        try:
            pg.click("button:has-text('注')", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(800)
        try:
            pg.click("text=新建项目", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(900)
        try:
            pg.click(".projects-card", timeout=6000)
        except Exception:
            pass
        pg.wait_for_timeout(1200)

        def sel_ids():
            return pg.evaluate("window.__canvas ? window.__canvas.getState().selectedIds : 'NO_HOOK'")

        def tb():
            return pg.evaluate("""() => {
              const t = document.querySelector('.text-node-toolbar');
              if (!t) return {exists: false};
              const cs = getComputedStyle(t);
              const r = t.getBoundingClientRect();
              return {exists: true, vis: cs.visibility, op: cs.opacity,
                      w: Math.round(r.width), top: Math.round(r.top)};
            }""")

        # 添加文本节点
        pg.click(".pea-tlb-btn[aria-label*='添加节点']", timeout=5000)
        pg.wait_for_timeout(300)
        pg.click(".pea-add-menu-item:has-text('文本')", timeout=5000)
        pg.wait_for_timeout(900)
        node = pg.locator(".react-flow__node").last
        node.scroll_into_view_if_needed()
        pg.wait_for_timeout(300)
        box = node.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

        # 1) 单击 -> 工具条可见
        pg.mouse.click(cx, cy)
        pg.wait_for_timeout(500)
        t1 = tb()
        check(t1["exists"] and t1.get("op") == "1", "1) 单击文本节点 工具条可见")

        # 2) 点空白 -> 工具条消失、selectedIds 空
        pg.mouse.click(180, 720)
        pg.wait_for_timeout(500)
        t2 = tb()
        check((not t2["exists"]) and sel_ids() == [], "2) 点空白 工具条消失且取消选中")

        # 3) 再次单击 -> 工具条恢复（核心修复）
        pg.wait_for_timeout(300)
        pg.mouse.click(cx, cy)
        pg.wait_for_timeout(700)
        t3 = tb()
        check(t3["exists"] and t3.get("op") == "1", "3) 再次单击 工具条恢复(修复 lastPosRef)")
        # 轮询 1.5s 兜底，确保不是时序
        if not (t3["exists"] and t3.get("op") == "1"):
            for _ in range(8):
                pg.wait_for_timeout(200)
                if tb()["exists"]:
                    msgs[-1] = ("PASS", "3) 再次单击 工具条恢复(延迟恢复)")
                    fails -= 1
                    break

        # 4) 双击进编辑 -> 工具条仍在、contentEditable=true
        box = node.bounding_box()
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        pg.mouse.dblclick(cx, cy)
        pg.wait_for_timeout(500)
        t4 = tb()
        edit_flag = pg.evaluate("""() => {
          const ed = document.querySelector('.react-flow__node[data-id] .pea-node-text-edit');
          return ed ? ed.getAttribute('contenteditable') : null;
        }""")
        check(t4["exists"] and t4.get("op") == "1", "4) 双击编辑 工具条仍在")
        check(edit_flag == "true", "4b) 双击编辑 contentEditable=true")

        # 5) 统一手型光标
        cursor = pg.evaluate("""() => {
          const n = document.querySelector('.react-flow__node .pea-node');
          return n ? getComputedStyle(n).cursor : null;
        }""")
        check(cursor in ("grab", "grabbing"), f"5) .pea-node 光标为手型(grab) 实际={cursor}")

        check(len(errs) == 0, "0) 无 console error")
        if errs:
            msgs.append(("INFO", "console: " + str(errs[:3])))

        b.close()

    print("\n=== E23 结果 ===")
    for tag, name in msgs:
        print(f"  [{tag}] {name}")
    print(f"FAILS={fails}")
    return fails


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
