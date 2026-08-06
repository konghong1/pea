"""
裁切态强制刷新回归验证。
场景：选中 AI 生成节点 → 点裁剪进入裁切模式 → 不取消、强制刷新页面 → 重新选中节点。
期望：
  - 刷新后裁切浮层/工具条完全消失（无残留）
  - 编辑框重新可见（未再被卡死）
  - 图片仍是原图（裁切未半路落盘）
  - 节点不带 is-cropping 类
"""
import time
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
PNG_1x1 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def log(*a):
    print(*a, flush=True)


def main():
    results = []
    console_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        def _is_real_err(m):
            if m.type != "error":
                return False
            t = m.text
            if "Failed to load resource" in t:
                return False
            return True

        page.on("console", lambda m: console_errors.append(m.text) if _is_real_err(m) else None)
        page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))

        page.context.add_init_script('() => { localStorage.setItem("__peaDevHooks", "1"); }')
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(600)

        try:
            page.get_by_role("button", name="没有账号？去注册").first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f"ref_{ts}@pea.dev")
            page.fill('input[placeholder="至少 8 位"]', "Password123")
            page.locator("form button[type=submit]").click()
            page.wait_for_timeout(4000)
            page.locator("text=新建项目").first.click(timeout=5000)
            page.wait_for_timeout(1800)
        except Exception as e:
            log(f"[warn] login/nav: {e}")

        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        # 强制开启 dev hooks 并重载，确保 window.__canvas 暴露
        page.evaluate("() => localStorage.setItem('__peaDevHooks', '1')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(800)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        ai_id = page.evaluate(
            """(png) => {
                const c = window.__canvas;
                const id = c.getState().addNode(
                    { kind: 'image', resultUrl: png, resultUrls: [png], prompt: '一只猫', label: 'AI图' },
                    { x: 80, y: 80 }
                );
                return id;
            }""",
            PNG_1x1,
        )
        page.wait_for_timeout(600)
        try:
            page.evaluate("() => window.__peaFitView && window.__peaFitView()")
        except Exception:
            pass
        page.wait_for_timeout(500)

        def select_node(nid):
            page.locator(f'.react-flow__node[data-id="{nid}"]').click()
            page.wait_for_timeout(800)

        def state():
            return page.evaluate(
                """() => {
                    const node = document.querySelector('.react-flow__node.selected')
                                  || document.querySelector('.react-flow__node');
                    if (!node) return { node: false };
                    const anchor = node.querySelector('.pea-node-editor-anchor');
                    const acs = anchor ? getComputedStyle(anchor) : null;
                    const overlay = node.querySelector('.pea-crop-overlay-inline');
                    const toolbar = node.querySelector('.pea-crop-toolbar-inline');
                    const img = node.querySelector('img');
                    const peaNode = node.querySelector('.pea-node');
                    return {
                        node: true,
                        isCroppingClass: peaNode ? peaNode.classList.contains('is-cropping') : null,
                        editorDisplay: acs ? acs.display : 'NO_ANCHOR',
                        editorHasChild: anchor ? anchor.childElementCount > 0 : false,
                        overlay: !!overlay,
                        toolbar: !!toolbar,
                        imgSrc: img ? img.getAttribute('src') : null,
                    };
                }"""
            )

        # 基线：选中 AI 节点
        select_node(ai_id)
        base = state()
        ok_base = base.get("editorDisplay") != "none" and base.get("editorHasChild")
        results.append(("基线 选中 AI 节点 → 编辑框可见", ok_base, base))

        # 点裁剪进入裁切模式
        page.locator('button[aria-label="裁剪"]').click()
        page.wait_for_timeout(900)
        in_crop = state()
        ok_in = in_crop.get("editorDisplay") == "none" and in_crop.get("overlay") and in_crop.get("toolbar")
        results.append(("点裁剪 → 进入裁切模式(编辑框隐藏+浮层+工具条)", ok_in, in_crop))
        page.screenshot(path="verify/shots/crop_refresh_01_in_crop.png", full_page=False)

        # 【关键】不取消，强制刷新
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(800)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)
        # 刷新后重新暴露 __canvas 并选中节点
        page.evaluate("() => localStorage.setItem('__peaDevHooks', '1')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(800)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)
        select_node(ai_id)

        after = state()
        ok_after_editor = after.get("editorDisplay") != "none" and after.get("editorHasChild")
        ok_after_clean = (not after.get("overlay")) and (not after.get("toolbar")) and (after.get("isCroppingClass") is False)
        ok_after_img = after.get("imgSrc") == base.get("imgSrc")
        results.append(("刷新后 编辑框重新可见", ok_after_editor, after))
        results.append(("刷新后 无裁切残留(浮层/工具条/类全清)", ok_after_clean, after))
        results.append(("刷新后 图片仍是原图(未半路落盘)", ok_after_img, {"before": base.get("imgSrc"), "after": after.get("imgSrc")}))
        page.screenshot(path="verify/shots/crop_refresh_02_after_reload.png", full_page=False)

        all_pass = all(r[1] for r in results)
        log("\n=== 裁切态强制刷新 验证结果 ===")
        for name, ok, detail in results:
            log(f"  {'✅' if ok else '❌'} {name}: {detail}")
        log(f"\nConsole errors: {len(console_errors)}")
        for e in console_errors[:10]:
            log(f"   - {e}")
        log(f"\n总判定: {'ALL PASS ✅' if all_pass else 'SOME FAILED ❌'}")
        browser.close()
        sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
