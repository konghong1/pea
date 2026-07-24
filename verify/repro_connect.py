import os, random, string, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"

def ts_email():
    return f"e{int(time.time()*1000)}@pea.ai"

def shot(page, name):
    os.makedirs("c:/workspace/pea/verify/shots", exist_ok=True)
    p = f"c:/workspace/pea/verify/shots/{name}.png"
    page.screenshot(path=p)
    print(f"  [shot] {name}.png")
    return p

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(800)
        # 登录
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"rc_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "RC")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        shot(page, "repro_00_after_login")

        # 添加 text 节点
        page.locator(".pea-toolbar").get_by_role("button", name="添加节点（双击画布也可打开）", exact=True).first.click()
        page.wait_for_timeout(400)
        page.locator(".pea-add-menu-item", has_text="文本").first.click()
        page.wait_for_timeout(500)

        # 添加 image 节点
        page.locator(".pea-toolbar").get_by_role("button", name="添加节点（双击画布也可打开）", exact=True).first.click()
        page.wait_for_timeout(400)
        page.locator(".pea-add-menu-item", has_text="图片").first.click()
        page.wait_for_timeout(600)
        shot(page, "repro_01_two_nodes")

        nodes = page.locator(".react-flow__node")
        print("节点数:", nodes.count())

        # 悬停 node1 让手柄显现，再精确点中右侧 source handle
        n1 = nodes.nth(0)
        n2 = nodes.nth(1)
        b1 = n1.bounding_box()
        b2 = n2.bounding_box()

        # 先选中 node1，使其 handle 显形（.selected .pea-handle 变 22px）
        page.mouse.click(b1["x"] + b1["width"]/2, b1["y"] + b1["height"]/2)
        page.wait_for_timeout(300)

        # 取 node1 的 source handle（右侧）精确坐标
        src_handle = n1.locator(".react-flow__handle.source").first
        hb = src_handle.bounding_box()
        print("source handle box:", hb)
        if not hb:
            # fallback: 节点右缘外 2px 中部
            hx = b1["x"] + b1["width"] + 2
            hy = b1["y"] + b1["height"] / 2
        else:
            hx = hb["x"] + hb["width"] / 2
            hy = hb["y"] + hb["height"] / 2
        print(f"从 handle ({hx:.0f},{hy:.0f}) 开始连线拖到 node2...")

        page.mouse.move(hx, hy)
        page.mouse.down()
        page.wait_for_timeout(150)
        # 拖到一半
        midx = (hx + b2["x"] + b2["width"]/2) / 2
        midy = (hy + b2["y"] + b2["height"]/2) / 2
        page.mouse.move(midx, midy, steps=5)
        page.wait_for_timeout(200)
        shot(page, "repro_02_connecting_mid")
        # 检查连线过程中节点是否可见
        vis_during = []
        for i in range(nodes.count()):
            el = nodes.nth(i)
            try:
                box = el.bounding_box()
                style = el.evaluate("e => getComputedStyle(e).opacity")
                vis_during.append((i, box is not None, style))
            except Exception as ex:
                vis_during.append((i, False, str(ex)))
        print("连线中节点可见性:", vis_during)
        # 拖到 node2 上释放
        page.mouse.move(b2["x"] + b2["width"]/2, b2["y"] + b2["height"]/2, steps=5)
        page.wait_for_timeout(150)
        page.mouse.up()
        page.wait_for_timeout(400)
        shot(page, "repro_03_after_connect")
        edges = page.locator(".react-flow__edge").count()
        print("边数量:", edges)

        print("\n=== 控制台错误 ===")
        for e in errors[:20]:
            print("  ", e)

        b.close()

if __name__ == "__main__":
    main()
