"""验证连接点升级：反缩放恒定尺寸 / 悬停放大 / 间距恒定 / 科技图标渲染。
复用 debug_conn.py 的登录与建节点流程。
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time, json

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

def main():
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"])
        page = b.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)

        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"vh_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "VH")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        # 登录后落在工作空间页，需「新建项目」进入画布
        try:
            page.get_by_role("button", name="新建项目").first.click()
            page.wait_for_timeout(3000)
            # 如果出现画布选择/创建弹窗，确认
            for _ in range(3):
                if page.locator(".react-flow__viewport").count() > 0:
                    break
                # 可能需要再点一次或等加载
                page.wait_for_timeout(1000)
        except Exception:
            pass  # 已在画布则忽略
        page.wait_for_selector(".react-flow__viewport", timeout=20000)

        def add_at(label, x, y):
            page.mouse.dblclick(x, y)
            page.wait_for_timeout(350)
            page.locator(".pea-add-menu-item", has_text=label).first.click()
            page.wait_for_timeout(600)

        add_at("文本", 360, 300)
        add_at("图片", 1040, 300)
        page.wait_for_timeout(800)
        nodes = page.locator(".react-flow__node")
        out["node_count"] = nodes.count()
        page.wait_for_timeout(400)

        src = nodes.nth(0).locator(".react-flow__handle.source").first

        def measure(tag):
            hb = src.bounding_box()
            nb = nodes.nth(0).bounding_box()
            nb_right = nb["x"] + nb["width"]
            near_gap = (hb["x"]) - nb_right          # 节点右缘 -> 手柄近缘
            center_gap = (hb["x"] + hb["width"]/2) - nb_right
            glyph = page.locator(".pea-handle-glyph").count()
            out[tag] = {
                "handle_w": round(hb["width"], 2),
                "handle_h": round(hb["height"], 2),
                "near_gap_px": round(near_gap, 2),
                "center_gap_px": round(center_gap, 2),
                "glyph_svg_count": glyph,
            }
            return out[tag]

        # 1) 默认缩放
        m1 = measure("zoom_default")
        page.screenshot(path=str(SHOTS/"v1_default.png"))

        # 2) 悬停节点（放大反馈）——在缩放前做，确保节点在视口内
        nodes.nth(0).hover()
        page.wait_for_timeout(400)
        m3 = measure("hover")
        page.screenshot(path=str(SHOTS/"v3_hover.png"))

        # 3) 缩小画布（滚轮向下多次）
        page.mouse.move(720, 450)
        for _ in range(6):
            page.mouse.wheel(0, 400)
            page.wait_for_timeout(120)
        page.wait_for_timeout(400)
        m2 = measure("zoom_out")
        page.screenshot(path=str(SHOTS/"v2_zoomout.png"))

        # 4) 连线进行中（拖拽源手柄）
        hb = src.bounding_box()
        page.mouse.move(hb["x"]+hb["width"]/2, hb["y"]+hb["height"]/2)
        page.mouse.down()
        page.wait_for_timeout(200)
        m4 = measure("connecting")
        page.mouse.up()
        page.wait_for_timeout(300)

        out["page_errors"] = errors[:10]
        b.close()

    print(json.dumps(out, indent=2, ensure_ascii=False))
    # 自动断言
    checks = []
    checks.append(("默认 ~13px 级尺寸", abs(m1["handle_w"]-13) < 4))
    checks.append(("缩小后尺寸恒定(±4px)", abs(m2["handle_w"]-m1["handle_w"]) < 4))
    checks.append(("悬停放大", m3["handle_w"] > m1["handle_w"] + 3))
    checks.append(("缩小后间距恒定(±6px)", abs(m2["near_gap_px"]-m1["near_gap_px"]) < 6))
    checks.append(("间距明显(>6px)", m1["near_gap_px"] > 6))
    checks.append(("科技图标 SVG 渲染", m1["glyph_svg_count"] > 0))
    checks.append(("无运行时报错", len(errors) == 0))
    print("\n=== 断言 ===")
    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("\nRESULT:", "ALL PASS" if ok else "HAS FAIL")

if __name__ == "__main__":
    main()
