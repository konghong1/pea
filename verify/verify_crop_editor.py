"""
裁切模式编辑框显隐验证（精准回归测试）。
验证三个用例：
  A. 脏数据回归：AI 生成节点被写入 isCropping:true（历史脏数据）→ 选中后编辑框【必须可见】
  B. 功能正常：AI 生成节点 → 选中编辑框可见 → 点裁剪编辑框隐藏 → 取消裁剪编辑框恢复
  C. 不变行为：上传节点 → 编辑框【始终隐藏】

通过 window.__canvas 注入节点，避免依赖真实生成/上传流程。
"""
import time
import json
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
        # 过滤测试注入假 fileKey/URL 导致的资源 400（非代码缺陷）
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

        # 快速注册 + 新建项目
        try:
            page.get_by_role("button", name="没有账号？去注册").first.click(timeout=3000)
            page.wait_for_timeout(300)
            ts = int(time.time())
            page.fill('input[placeholder="you@pea.ai"]', f"crop_{ts}@pea.dev")
            page.fill('input[placeholder="至少 8 位"]', "Password123")
            page.locator("form button[type=submit]").click()
            page.wait_for_timeout(4000)
            page.locator("text=新建项目").first.click(timeout=5000)
            page.wait_for_timeout(1800)
        except Exception as e:
            log(f"[warn] login/nav: {e}")

        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        # 强制开启 dev hooks 并重载，确保 window.__canvas 暴露（注册流程可能清过 localStorage）
        page.evaluate("() => localStorage.setItem('__peaDevHooks', '1')")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(800)
        page.wait_for_selector(".react-flow__viewport", timeout=15000)
        page.wait_for_timeout(800)

        # ── 注入 AI 生成图片节点（resultUrl 有值、无 fileKey → 选中应显示编辑框）
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
            el = page.locator(f'.react-flow__node[data-id="{nid}"]')
            el.click()
            page.wait_for_timeout(700)

        def editor_state():
            return page.evaluate(
                """() => {
                    const anchor = document.querySelector('.pea-node.selected .pea-node-editor-anchor')
                                  || document.querySelector('.pea-node-editor-anchor');
                    if (!anchor) return { exists: false };
                    const cs = getComputedStyle(anchor);
                    return {
                        exists: true,
                        display: cs.display,
                        hasChild: anchor.childElementCount > 0,
                        h: anchor.getBoundingClientRect().height,
                    };
                }"""
            )

        # ── 用例 A：模拟脏数据 isCropping:true
        page.evaluate(
            """(args) => { window.__canvas.getState().updateNodeData(args[0], { isCropping: true }); }""",
            [ai_id],
        )
        page.wait_for_timeout(300)
        select_node(ai_id)
        st_a = editor_state()
        ok_a = st_a.get("exists") and st_a.get("display") != "none" and st_a.get("hasChild")
        results.append(("A 脏数据 isCropping:true → 编辑框仍可见", ok_a, st_a))
        page.screenshot(path="verify/shots/crop_editor_A_stale.png", full_page=False)

        # ── 用例 B：功能正常（先清掉脏数据）
        page.evaluate(
            """(args) => { window.__canvas.getState().updateNodeData(args[0], { isCropping: undefined }); }""",
            [ai_id],
        )
        page.wait_for_timeout(300)
        select_node(ai_id)
        st_b1 = editor_state()
        ok_b1 = st_b1.get("display") != "none" and st_b1.get("hasChild")
        results.append(("B1 选中 AI 节点 → 编辑框可见", ok_b1, st_b1))

        # 点裁剪（精确定位真正的功能条按钮，避开节点容器本身）
        page.locator('button[aria-label="裁剪"]').click()
        page.wait_for_timeout(900)
        st_b2 = editor_state()
        ok_b2 = st_b2.get("display") == "none" or not st_b2.get("hasChild")
        results.append(("B2 点裁剪 → 编辑框隐藏", ok_b2, st_b2))

        # 裁剪工具条应可见
        crop_bar = page.evaluate(
            """() => {
                const t = document.querySelector('.pea-crop-toolbar-inline');
                if (!t) return { exists: false };
                const r = t.getBoundingClientRect();
                return { exists: true, w: Math.round(r.width), h: Math.round(r.height), vis: getComputedStyle(t).visibility };
            }"""
        )
        ok_bar = crop_bar.get("exists") and crop_bar.get("w", 0) > 50 and crop_bar.get("h", 0) > 10
        results.append(("B2b 裁剪工具条可见", ok_bar, crop_bar))
        page.screenshot(path="verify/shots/crop_editor_B_cropping.png", full_page=False)

        # 取消裁剪
        page.get_by_role("button", name="取消裁剪").click()
        page.wait_for_timeout(900)
        st_b3 = editor_state()
        ok_b3 = st_b3.get("display") != "none" and st_b3.get("hasChild")
        results.append(("B3 取消裁剪 → 编辑框恢复", ok_b3, st_b3))

        # ── 用例 C：上传节点编辑框始终隐藏
        up_id = page.evaluate(
            """(args) => {
                const c = window.__canvas;
                const id = c.getState().addNode(
                    { kind: 'image', fileKey: 'u/test/upload.png', url: args[0], label: '上传图' },
                    { x: 420, y: 80 }
                );
                return id;
            }""",
            PNG_1x1,
        )
        page.wait_for_timeout(500)
        try:
            page.evaluate("() => window.__peaFitView && window.__peaFitView()")
        except Exception:
            pass
        page.wait_for_timeout(400)
        select_node(up_id)
        st_c = editor_state()
        # 上传节点：NodeChatPrompt 直接 return null，anchor 无 child
        ok_c = (not st_c.get("hasChild")) or st_c.get("display") == "none"
        results.append(("C 上传节点 → 编辑框隐藏（不变行为）", ok_c, st_c))

        browser.close()

    # ── 输出
    log("\n=== 裁切编辑框显隐验证 ===")
    all_pass = True
    for name, ok, detail in results:
        status = "✅" if ok else "❌"
        log(f"  {status} {name}  {json.dumps(detail, ensure_ascii=False)}")
        if not ok:
            all_pass = False
    log(f"\nConsole errors: {len(console_errors)}")
    for e in console_errors[:10]:
        log(f"   ⚠️ {e}")
    if console_errors:
        all_pass = False
    log(f"\n结果: {'全部通过 ✅' if all_pass else '存在失败 ❌'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
