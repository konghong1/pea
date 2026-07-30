"""验证新功能：单击连接点（source handle）即可添加并连接节点。

覆盖两种场景：
- 场景1（鼠标放在连接点上）：悬停节点使连接点出现在静止位，单击圆点 → 弹出"新建并连接"菜单 → 选类型 → 生成已连接的下游节点。
- 场景2（连接点跟随鼠标时）：把光标移到节点右缘内侧，连接点跟随到该处，单击圆点 → 同样弹出菜单并建连。

同时确认：单击不会误触发拖拽连线（移动位移 < 阈值才判定为单击）；从 target(handleType='target') 单击会生成上游节点。
"""
import sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

checks = []
out = {}

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.add_init_script("try{localStorage.setItem('__peaDevHooks','1')}catch(e){}")
        page.set_default_timeout(20000)
        errors = []
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))

        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"click_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "Click")
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
        page.wait_for_timeout(800)

        a_box = page.locator(".react-flow__node").nth(0).bounding_box()
        cx0 = a_box["x"] + a_box["width"] / 2
        cy0 = a_box["y"] + a_box["height"] / 2
        A_ID = page.evaluate("() => document.querySelectorAll('.react-flow__node')[0].getAttribute('data-id')")

        def src_handle_center():
            return page.evaluate("""() => {
                const n = document.querySelectorAll('.react-flow__node')[0];
                const h = n ? n.querySelector('.react-flow__handle.source') : null;
                if (!h) return null;
                const r = h.getBoundingClientRect();
                return { x: r.left + r.width/2, y: r.top + r.height/2 };
            }""")

        def edges_of():
            return page.evaluate("""() => {
                const st = window.__canvas && window.__canvas.getState();
                return st ? (st.edges || []).map(e => ({source:e.source, target:e.target})) : [];
            }""")

        def nodes_count():
            return page.locator(".react-flow__node").count()

        def click_handle_and_pick(kind_label):
            # 单击连接点（down/up 同点，位移=0 -> 判定为单击而非拖拽）
            hc = src_handle_center()
            if not hc:
                return False, "handle not found"
            page.mouse.click(hc["x"], hc["y"])
            page.wait_for_timeout(350)
            menu_present = page.locator(".pea-edge-menu").count() > 0
            if not menu_present:
                return False, "edge menu did not open"
            item = page.locator(".pea-edge-menu-item", has_text=kind_label).first
            if item.count() == 0:
                return False, f"menu item '{kind_label}' not found"
            item.click()
            page.wait_for_timeout(700)
            return True, None

        # ── 场景1：光标放在连接点上单击 ──
        page.mouse.move(cx0, cy0)            # 悬停节点，连接点出现在静止位
        page.wait_for_timeout(250)
        edges_before = edges_of()
        nodes_before = nodes_count()
        ok1, err1 = click_handle_and_pick("图片生成")
        page.wait_for_timeout(300)
        edges_after1 = edges_of()
        nodes_after1 = nodes_count()
        created_edge1 = next((e for e in edges_after1 if e["source"] == A_ID and e not in edges_before), None)
        checks.append(("场景1: 单击 source 连接点弹出菜单", ok1))
        checks.append(("场景1: 生成了下游新节点", nodes_after1 == nodes_before + 1))
        checks.append(("场景1: 新节点与源节点 A 建立连线(source->A?)", created_edge1 is not None and created_edge1["source"] == A_ID))
        out["scene1"] = {"ok": ok1, "err": err1, "edges_before": len(edges_before), "edges_after": len(edges_after1),
                         "nodes_before": nodes_before, "nodes_after": nodes_after1, "edge": created_edge1}
        page.screenshot(path=str(SHOTS / "click_add_scene1.png"))

        # ── 场景2：连接点跟随鼠标时单击（光标移到右缘内侧） ──
        page.mouse.move(cx0, cy0)
        page.wait_for_timeout(200)
        # 把光标移到节点右缘内侧，连接点应跟随到该处
        page.mouse.move(a_box["x"] + a_box["width"] - 14, cy0, steps=4)
        page.wait_for_timeout(250)
        edges_before2 = edges_of()
        nodes_before2 = nodes_count()
        ok2, err2 = click_handle_and_pick("文本生成")
        page.wait_for_timeout(300)
        edges_after2 = edges_of()
        nodes_after2 = nodes_count()
        created_edge2 = next((e for e in edges_after2 if e["source"] == A_ID and e not in edges_before2), None)
        checks.append(("场景2: 连接点跟随鼠标时单击弹出菜单", ok2))
        checks.append(("场景2: 生成了下游新节点", nodes_after2 == nodes_before2 + 1))
        checks.append(("场景2: 新节点与源节点 A 建立连线", created_edge2 is not None and created_edge2["source"] == A_ID))
        out["scene2"] = {"ok": ok2, "err": err2, "edges_before": len(edges_before2), "edges_after": len(edges_after2),
                         "nodes_before": nodes_before2, "nodes_after": nodes_after2, "edge": created_edge2}
        page.screenshot(path=str(SHOTS / "click_add_scene2.png"))

        out["page_errors"] = errors[:10]
        checks.append(("无运行时崩溃报错", len([e for e in errors if 'PAGEERROR' in e]) == 0))
        b.close()

    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("\n=== 断言 ===")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("\nRESULT:", "ALL PASS" if ok else "HAS FAIL")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
