"""验证图片节点裁剪功能：
1. 注册并进入画布。
2. 添加图片节点并上传一张测试图。
3. 选中节点后点击功能条「裁剪」按钮。
4. 验证画布聚焦、裁剪浮层与裁剪框可见。
5. 拖动裁剪区、切换裁剪比例。
6. 点击「确认裁剪」生成名为「Clipping diagram」的输出节点。
7. 断言输出节点存在且包含图片，无 console error。
"""

from playwright.sync_api import sync_playwright, expect
from pathlib import Path
import time

ROOT = Path("D:/workspace/pea")
SHOTS = ROOT / "verify" / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

TEST_IMG = ROOT / "verify" / "test_crop_source.png"

def ensure_test_image():
    from PIL import Image, ImageDraw
    if TEST_IMG.exists():
        return
    img = Image.new("RGB", (600, 800), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 550, 750], fill=(200, 160, 120), outline=(255, 255, 255), width=4)
    draw.ellipse([150, 250, 450, 550], fill=(120, 180, 220))
    draw.text((200, 100), "CROP TEST", fill=(255, 255, 255))
    img.save(TEST_IMG)

errors: list[str] = []
console_msgs: list[str] = []


def on_console(msg):
    if msg.type == "error":
        errors.append(f"{msg.type}: {msg.text}")
    console_msgs.append(f"[{msg.type}] {msg.text}")


def on_pageerror(err):
    errors.append(f"pageerror: {err}")


def shot(page, name: str):
    p = SHOTS / f"crop_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"[shot] {p}")


def main():
    ensure_test_image()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        # 开启 dev hook，使验证脚本能控制视口缩放
        page.context.add_init_script("""() => {
          localStorage.setItem('__peaDevHooks', '1');
        }""")
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)

        # 注册
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"crop_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "Crop")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        # 注册后进入工作空间，需要新建项目才能打开画布
        page.locator("text=新建项目").first.click()
        page.wait_for_timeout(1500)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        shot(page, "01_default")

        # 添加图片节点
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator(".pea-add-menu-item", has_text="图片").first.click()
        page.wait_for_timeout(800)
        shot(page, "02_image_node_added")

        node = page.locator(".react-flow__node").first
        expect(node).to_be_visible()

        # 上传测试图到隐藏的文件输入框
        file_input = node.locator("input[type='file']")
        file_input.set_input_files(str(TEST_IMG))
        page.wait_for_timeout(1500)
        shot(page, "03_image_uploaded")

        # 选中节点以显示功能条（上传后可能已经选中）
        node.click()
        page.wait_for_timeout(300)

        # 记录源节点尺寸，用于后续“输出节点不应更大”断言
        src_box = node.bounding_box()
        src_area = (src_box["width"] * src_box["height"]) if src_box else 0
        print(f"[check] source node size: {src_box['width']:.1f}x{src_box['height']:.1f}")

        # 点击「裁剪」按钮
        crop_btn = page.locator(".pea-node-result-toolbar").get_by_role("button", name="裁剪")
        expect(crop_btn).to_be_visible()
        crop_btn.click()
        page.wait_for_timeout(1400)
        shot(page, "04_crop_overlay")

        overlay = page.locator(".pea-crop-overlay-inline")
        expect(overlay).to_be_visible()
        print("[check] crop overlay visible: True")

        frame = overlay.locator(".pea-crop-frame")
        expect(frame).to_be_visible()
        print("[check] crop frame visible: True")

        handles = overlay.locator(".pea-crop-handle")
        expect(handles).to_have_count(4)
        print("[check] crop handles count: 4")

        # 裁剪时原节点功能条、收藏星标、替换按钮应隐藏
        expect(page.locator(".pea-node-result-toolbar")).not_to_be_visible()
        expect(page.locator(".pea-node-result-star")).not_to_be_visible()
        print("[check] node toolbar/star hidden during crop: True")

        # 裁剪时编辑框（节点输入栏）必须隐藏
        edit_box = page.locator(".node-input-bar")
        if edit_box.count() > 0 and edit_box.first.is_visible():
            errors.append("edit box (.node-input-bar) still visible during crop")
        print(f"[check] edit box hidden during crop: {not (edit_box.count() > 0 and edit_box.first.is_visible())}")

        # ── 核心几何断言：功能条必须在「节点框正下方」，不得压在被裁的图片上 ──
        crop_bar = page.locator(".pea-crop-toolbar-inline")
        expect(crop_bar).to_be_visible()

        geo = page.evaluate(
            """() => {
              const bar  = document.querySelector('.pea-crop-toolbar-inline');
              const card = document.querySelector('.pea-node.is-cropping .pea-node-body-card');
              const img  = document.querySelector('.pea-node.is-cropping img.pea-node-media-preview');
              if (!bar || !card || !img) return null;
              const b = bar.getBoundingClientRect();
              const c = card.getBoundingClientRect();
              const i = img.getBoundingClientRect();
              const cs = getComputedStyle(bar);
              const overlapsImage = !(b.right <= i.left || b.left >= i.right || b.bottom <= i.top || b.top >= i.bottom);
              return {
                barRect:  { x: b.x, y: b.y, w: b.width, h: b.height, top: b.top, bottom: b.bottom },
                cardRect: { top: c.top, bottom: c.bottom, left: c.left, right: c.right },
                imgRect:  { top: i.top, bottom: i.bottom },
                parentClass: bar.parentElement ? bar.parentElement.className : '',
                overlapsImage,
                gapBelowCard: b.top - c.bottom,
                barCenterX: b.left + b.width / 2,
                cardCenterX: c.left + c.width / 2,
                display: cs.display,
                flexWrap: cs.flexWrap,
                borderRadius: cs.borderRadius,
              };
            }"""
        )
        if not geo:
            errors.append("crop toolbar / node card / image not found for geometry check")
        else:
            print(f"[check] toolbar rect: {geo['barRect']['w']:.1f}x{geo['barRect']['h']:.1f} @y={geo['barRect']['y']:.1f}")
            print(f"[check] toolbar parent: {geo['parentClass']}")
            print(f"[check] gap below node card: {geo['gapBelowCard']:.1f}px")
            print(f"[check] overlaps image: {geo['overlapsImage']}")

            if "pea-crop-toolbar-anchor" not in geo["parentClass"]:
                errors.append(f"crop toolbar not mounted in node anchor (parent={geo['parentClass']})")
            if geo["overlapsImage"]:
                errors.append("crop toolbar overlaps the image being cropped (must sit below the node)")
            if geo["gapBelowCard"] < 0:
                errors.append(f"crop toolbar is not below node card (gap={geo['gapBelowCard']:.1f})")
            if geo["gapBelowCard"] > 60:
                errors.append(f"crop toolbar too far from node card (gap={geo['gapBelowCard']:.1f})")
            if abs(geo["barCenterX"] - geo["cardCenterX"]) > 4:
                errors.append(
                    f"crop toolbar not horizontally centered under node "
                    f"(bar={geo['barCenterX']:.1f} card={geo['cardCenterX']:.1f})"
                )
            # 样式搭配：单行胶囊，不允许换行/竖排
            if geo["barRect"]["h"] > 56:
                errors.append(f"crop toolbar height {geo['barRect']['h']:.1f}px suggests wrapped layout")

        # 三个按钮均为单行、宽度合理（防止历史上出现的文字竖排 bug）
        btn_geo = page.evaluate(
            """() => Array.from(document.querySelectorAll('.pea-crop-toolbar-inline .pea-crop-toolbar-btn'))
                 .map(b => { const r = b.getBoundingClientRect();
                             return { label: (b.getAttribute('aria-label')||'').trim(), w: r.width, h: r.height }; })"""
        )
        print(f"[check] toolbar buttons: {btn_geo}")
        for b in btn_geo:
            if b["h"] > 44:
                errors.append(f"toolbar button '{b['label']}' height {b['h']:.1f}px — text likely wrapped")

        # 拖动裁剪框（移动 60px 右下）
        box = frame.bounding_box()
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] / 2 + 60, box["y"] + box["height"] / 2 + 60, steps=8)
            page.mouse.up()
            page.wait_for_timeout(400)
            shot(page, "05_crop_moved")
            print("[check] crop frame moved: True")

        # 切换比例为 1:1
        ratio_btn = page.locator(".pea-crop-toolbar-inline").get_by_role("button", name="裁剪比例")
        ratio_btn.click()
        page.wait_for_timeout(300)
        page.locator(".ant-dropdown-menu-item", has_text="1 : 1").first.click()
        page.wait_for_timeout(400)
        shot(page, "06_ratio_1x1")
        print("[check] ratio switched to 1:1")

        # 确认裁剪
        confirm_btn = page.locator(".pea-crop-confirm")
        expect(confirm_btn).to_be_visible()
        confirm_btn.click()
        page.wait_for_timeout(1500)

        shot(page, "07_output_node")

        # 断言输出节点存在且名称为「Clipping diagram」
        output_node = page.locator(".react-flow__node", has_text="Clipping diagram")
        expect(output_node).to_be_visible()
        print("[check] output node 'Clipping diagram' visible: True")

        # 断言输出节点包含图片
        output_img = output_node.locator("img.pea-node-media-preview")
        expect(output_img).to_be_visible()
        src = output_img.get_attribute("src")
        print(f"[check] output image src present: {bool(src)}")

        # 断言输出节点尺寸不应大于源节点（在相同 viewport zoom 下重新测量源节点）
        source_node = page.locator(".react-flow__node").filter(has_not_text="Clipping diagram").first
        out_box = output_node.bounding_box()
        src_box_now = source_node.bounding_box()
        if out_box and src_box_now:
            out_area = out_box["width"] * out_box["height"]
            src_area_now = src_box_now["width"] * src_box_now["height"]
            print(f"[check] output node size: {out_box['width']:.1f}x{out_box['height']:.1f} area={out_area:.0f}")
            print(f"[check] source node size (current zoom): {src_box_now['width']:.1f}x{src_box_now['height']:.1f} area={src_area_now:.0f}")
            if out_area > src_area_now * 1.05:
                errors.append(f"output node area {out_area:.0f} larger than source area {src_area_now:.0f}")
        else:
            errors.append("could not measure output/source node size")

        # 断言存在从源节点到输出节点的连线
        edge_count = page.locator(".react-flow__edge").count()
        print(f"[check] edges count: {edge_count} (expected >= 1)")
        if edge_count < 1:
            errors.append("edge from source to clipping node not found")

        shot(page, "08_final")

        print(f"\n[TOTAL console errors]: {len(errors)}")
        for e in errors:
            print(f"  - {e}")

        log = SHOTS.parent / "crop_verify.log"
        log.write_text(
            f"timestamp={ts}\nerrors={len(errors)}\nconsole={len(console_msgs)}\n"
            + "\n".join(errors)
            + "\n--- last 30 console ---\n"
            + "\n".join(console_msgs[-30:]),
            encoding="utf-8",
        )
        print(f"[log] {log}")

        browser.close()
        if errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
