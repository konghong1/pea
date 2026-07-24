"""调试连线：记录 onConnectStart/onConnect/onConnectEnd，并尝试两种释放点：
A. 释放到目标节点中心（松模式应连接）
B. 释放到目标节点 target 手柄精确位置
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))

        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"dbg_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "DBG")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        def add_at(label, x, y):
            page.mouse.dblclick(x, y)
            page.wait_for_timeout(350)
            page.locator(".pea-add-menu-item", has_text=label).first.click()
            page.wait_for_timeout(600)

        add_at("文本", 300, 260)
        add_at("图片", 1080, 260)
        page.wait_for_timeout(800)
        nodes = page.locator(".react-flow__node")
        print("节点数:", nodes.count())

        # 选中 text 显形 handle
        tb = nodes.nth(0).bounding_box()
        page.mouse.click(tb["x"] + tb["width"]/2, tb["y"] + tb["height"]*0.62)
        page.wait_for_timeout(300)

        def try_connect(release_on_handle=False, tag=""):
            logs.clear()
            src = nodes.nth(0).locator(".react-flow__handle.source").first
            hb = src.bounding_box()
            hx, hy = hb["x"] + hb["width"]/2, hb["y"] + hb["height"]/2
            b2 = nodes.nth(1).bounding_box()
            page.mouse.move(hx, hy)
            page.mouse.down()
            page.wait_for_timeout(150)
            page.mouse.move((hx + b2["x"]+b2["width"]/2)/2, (hy + b2["y"]+b2["height"]/2)/2, steps=6)
            page.wait_for_timeout(150)
            if release_on_handle:
                tgt = nodes.nth(1).locator(".react-flow__handle.target").first
                tb2 = tgt.bounding_box()
                rx, ry = tb2["x"]+tb2["width"]/2, tb2["y"]+tb2["height"]/2
            else:
                rx, ry = b2["x"]+b2["width"]/2, b2["y"]+b2["height"]/2
            page.mouse.move(rx, ry, steps=6)
            page.wait_for_timeout(150)
            page.mouse.up()
            page.wait_for_timeout(500)
            edges = page.locator(".react-flow__edge").count()
            print(f"\n=== 尝试 {tag} (release_on_handle={release_on_handle}) 边数量={edges} ===")
            for l in logs:
                if "CONN" in l:
                    print("   ", l)
            return edges

        e1 = try_connect(False, "A-释放到节点中心")
        e2 = try_connect(True, "B-释放到target手柄")

        print(f"\n结果: A={e1} B={e2}")
        b.close()

if __name__ == "__main__":
    main()
