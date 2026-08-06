"""裁切 UI 快速验证：只检查裁切模式下的视觉正确性。
   - 工具栏是否可见、位置是否在节点下方
   - 裁切框/遮罩/把手是否完整渲染
   - 按钮文字是否换行
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


def shot(page, name):
    p = SHOTS / f"crop_ui_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    print(f"[shot] {p}")


def main():
    ensure_test_image()
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.context.add_init_script("""() => {
          localStorage.setItem('__peaDevHooks', '1');
        }""")
        page.goto("http://localhost:8088", wait_until="networkidle")
        page.wait_for_timeout(600)

        # 注册/登录
        try:
            page.get_by_role("button", name="没有账号？去注册").first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f"cui_{ts}@pea.dev")
            page.fill('input[placeholder="至少 8 位"]', "Password123")
            page.locator("form button[type=submit]").click()
            page.wait_for_timeout(4000)
            page.locator("text=新建项目").first.click(timeout=5000)
            page.wait_for_timeout(1500)
        except Exception:
            # 可能已登录，直接进入
            pass

        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        shot(page, "00_canvas")

        # 添加图片节点
        page.locator('.pea-tlb-btn[aria-label="添加节点"]').first.click()
        page.wait_for_timeout(500)
        page.locator(".pea-add-menu-item", has_text="图片").first.click()
        page.wait_for_timeout(800)

        node = page.locator(".react-flow__node").first
        expect(node).to_be_visible()

        # 上传测试图
        file_input = node.locator("input[type='file']")
        file_input.set_input_files(str(TEST_IMG))
        page.wait_for_timeout(1500)
        shot(page, "01_uploaded")

        # 选中节点
        node.click()
        page.wait_for_timeout(400)

        # 点击裁剪按钮
        crop_btn = page.locator(".pea-node-result-toolbar").get_by_role("button", name="裁剪")
        expect(crop_btn).to_be_visible(timeout=3000)
        crop_btn.click()
        page.wait_for_timeout(1400)
        shot(page, "02_crop_mode")

        # ═══════════════════ 核心检查 ═══════════════════

        # 1. overlay 是否存在且可见
        overlay = page.locator(".pea-crop-overlay-inline")
        if overlay.count() == 0:
            errors.append("❌ .pea-crop-overlay-inline 不存在！裁剪浮层未渲染")
            shot(page, "FAIL_no_overlay")
            print("\n".join(errors))
            browser.close()
            return
        if not overlay.first.is_visible():
            errors.append("❌ overlay 存在但不可见（可能被隐藏或尺寸为0）")

        # 2. 裁剪框是否存在
        frame = overlay.locator(".pea-crop-frame")
        if frame.count() == 0 or not frame.first.is_visible():
            errors.append("❌ .pea-crop-frame 不存在或不可见")
        else:
            fb = frame.bounding_box()
            print(f"[OK] 裁剪框: {fb['width']:.0f}x{fb['height']:.0f} @ ({fb['x']:.0f},{fb['y']:.0f})")

        # 3. 四角把手
        handles = overlay.locator(".pea-crop-handle")
        hc = handles.count()
        if hc != 4:
            errors.append(f"❌ 把手数量={hc}，期望4")
        else:
            print(f"[OK] 4个把手均存在")

        # 4. 遮罩块（top/bottom/left/right）
        masks = overlay.locator(".pea-crop-mask")
        mc = masks.count()
        if mc != 4:
            errors.append(f"❌ 遮罩数量={mc}，期望4")
        else:
            print(f"[OK] 4个遮罩块均存在")

        # 5. ⭐ 工具栏 — 最关键的检查
        toolbar = page.locator(".pea-crop-toolbar-inline")
        if toolbar.count() == 0:
            errors.append("❌ .pea-crop-toolbar-inline 不存在！工具栏未渲染")
            shot(page, "FAIL_no_toolbar")
        elif not toolbar.first.is_visible():
            # 即使 DOM 存在也可能不可见 — 检查原因
            tb_info = page.evaluate("""() => {
                const el = document.querySelector('.pea-crop-toolbar-inline');
                if (!el) return { exists: false };
                const r = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                const parent = el.parentElement;
                const pr = parent ? parent.getBoundingClientRect() : null;
                const pcs = parent ? getComputedStyle(parent) : null;
                return {
                    exists: true,
                    rect: { x: r.x, y: r.y, w: r.width, h: r.height },
                    style: {
                        display: cs.display,
                        visibility: cs.visibility,
                        opacity: cs.opacity,
                        position: cs.position,
                        bottom: cs.bottom,
                        left: cs.left,
                        transform: cs.transform,
                        zIndex: cs.zIndex,
                    },
                    parentTag: parent ? parent.tagName : null,
                    parentClass: parent ? parent.className : null,
                    parentRect: pr ? { x: pr.x, y: pr.y, w: pr.width, h: pr.height } : null,
                    parentOverflow: pcs ? pcs.overflow : null,
                    parentPosition: pcs ? pcs.position : null,
                };
            }""")
            print(f"[INFO] toolbar DOM 存在但不可见:")
            print(f"      rect=({tb_info['rect']['x']:.1f},{tb_info['rect']['y']:.1f}) {tb_info['rect']['w']:.1f}x{tb_info['rect']['h']:.1f}")
            print(f"      display={tb_info['style']['display']} vis={tb_info['style']['visibility']} op={tb_info['style']['opacity']}")
            print(f"      pos={tb_info['style']['position']} bottom={tb_info['style']['bottom']} left={tb_info['style']['left']}")
            print(f"      transform={tb_info['style']['transform']}")
            print(f"      parent=<{tb_info['parentTag']}> class='{tb_info['parentClass']}'")
            print(f"      parent overflow={tb_info['parentOverflow']} position={tb_info['parentPosition']}")
            if tb_info['parentRect']:
                print(f"      parent rect=({tb_info['parentRect']['x']:.1f},{tb_info['parentRect']['y']:.1f}) {tb_info['parentRect']['w']:.1f}x{tb_info['parentRect']['h']:.1f}")

            if tb_info['rect']['h'] == 0 or tb_info['rect']['w'] == 0:
                errors.append("❌ 工具栏尺寸为0 — 可能在可视区域外或被 overflow:hidden 裁切")
            elif tb_info['rect']['y'] < 0 or tb_info['rect']['bottom'] > 900:
                errors.append(f"❌ 工具栏在视口外 y={tb_info['rect']['y']:.1f} bottom={tb_info.get('rect',{}).get('bottom','?')}")
            else:
                errors.append(f"❌ 工具栏不可见（原因需进一步排查）")
        else:
            tb_box = toolbar.bounding_box()
            btns = toolbar.locator(".pea-crop-toolbar-btn")
            btn_count = btns.count()
            btn_info = page.evaluate(
                """() => Array.from(document.querySelectorAll('.pea-crop-toolbar-inline .pea-crop-toolbar-btn'))
                     .map(b => { const r = b.getBoundingClientRect();
                               return { label: (b.getAttribute('aria-label')||'').trim(),
                                        w: r.width, h: r.height }; })"""
            )
            print(f"[OK] 工具栏可见: {tb_box['width']:.0f}x{tb_box['height']:.0f} @ ({tb_box['x']:.0f},{tb_box['y']:.0f})")
            print(f"[OK] 按钮: {btn_count}个, 详情={btn_info}")

            for b in btn_info:
                if b["h"] > 44:
                    errors.append(f"⚠️ 按钮 '{b['label']}' 高度={b['h']:.0f}px（可能换行）")

        # 6. 几何关系检查
        geo = page.evaluate(
            """() => {
              const bar  = document.querySelector('.pea-crop-toolbar-inline');
              const card = document.querySelector('.pea-node.is-cropping .pea-node-body-card');
              const overlay = document.querySelector('.pea-crop-overlay-inline');
              if (!bar || !card || !overlay) return null;
              const b = bar.getBoundingClientRect();
              const c = card.getBoundingClientRect();
              const o = overlay.getBoundingClientRect();
              return {
                  bar:  { x: b.x, y: b.y, w: b.width, h: b.height, top: b.top, bottom: b.bottom, left: b.left, right: b.right },
                  card: { top: c.top, bottom: c.bottom, left: c.left, right: c.left, w: c.width, h: c.height },
                  overlay: { top: o.top, bottom: o.bottom, w: o.width, h: o.height },
                  gapBarToCardBottom: b.top - c.bottom,
                  barInsideOverlay: b.top >= o.top && b.bottom <= o.bottom + 60,
              };
          }"""
        )
        if geo:
            print(f"\n[几何]")
            print(f"  overlay: {geo['overlay']['w']:.0f}x{geo['overlay']['h']:.0f}")
            print(f"  card:    {geo['card']['w']:.0f}x{geo['card']['h']:.0f}")
            print(f"  bar→card底部间距: {geo['gapBarToCardBottom']:.1f}px")
            if geo['gapBarToCardBottom'] < -10:
                errors.append(f"⚠️ 工具栏与卡片重叠（gap={geo['gapBarToCardBottom']:.1f}px）")
            elif geo['gapBarToCardBottom'] > 80:
                errors.append(f"⚠️ 工具栏离卡片太远（gap={geo['gapBarToCardBottom']:.1f}px）")

        # 7. 锚点元素检查（应该不存在或不占空间）
        anchor = page.locator(".pea-crop-toolbar-anchor")
        if anchor.count() > 0:
            ab = anchor.first.bounding_box()
            if ab and ab["height"] > 5:
                errors.append(f"⚠️ 锚点元素仍占空间: {ab['width']:.0f}x{ab['height']:.0f}")
            else:
                print("[OK] 锚点元素存在但不占空间（display:none 或 size=0）")
        else:
            print("[OK] 锚点元素已移除")

        shot(page, "03_final_check")

        # 输出结果
        print(f"\n{'='*50}")
        if errors:
            print(f"❌ 发现 {len(errors)} 个问题:")
            for e in errors:
                print(f"  {e}")
        else:
            print("✅ 所有检查通过！")

        browser.close()
        if errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
