# -*- coding: utf-8 -*-
"""
验证: 选中节点后按 Delete 能删除节点。
场景:
  1. 点击 AI 图片节点 → 输入栏弹出并自动聚焦(空) → 按 Delete → 节点被删除
  2. 点击文本节点 → 按 Delete → 节点被删除
  3. 安全性: 输入栏里有文字时按 Delete → 节点不被删除(Delete 用于编辑文本)
  4. 安全性: 空输入栏按 Backspace → 节点不被删除
"""
import time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOT = "verify/shots"


def log(msg):
    print(msg, flush=True)


def register(page):
    ts = int(time.time() * 1000) % 100000000
    email = f"vdel{ts}@t.com"
    pwd = "test1234"
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(700)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', email)
    page.fill('input[placeholder="至少 8 位"]', pwd)
    page.fill('input[placeholder="可选"]', "vdel")
    page.locator("form button[type=submit]").click()
    page.wait_for_function("() => !!localStorage.getItem('pea_token')", timeout=15000)
    log(f"[ok] registered {email}")


def enter_canvas(page):
    page.wait_for_selector('button:has-text("新建项目")', timeout=15000)
    page.click('button:has-text("新建项目")')
    page.wait_for_selector(".react-flow", timeout=15000)
    page.evaluate("() => { localStorage.__peaDevHooks = '1'; }")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector(".react-flow", timeout=15000)
    page.wait_for_function("() => !!window.__canvas", timeout=15000)
    log("[ok] canvas ready with dev hooks")


def inject_nodes(page):
    page.evaluate(
        """() => {
        const st = window.__canvas.getState();
        st.loadGraph([
          { id: 'ai1', type: 'pea', position: { x: 120, y: 120 },
            data: { label: 'AI图', kind: 'image', prompt: 'x',
                    resultUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
                    meta: { error: false } } },
          { id: 't1', type: 'pea', position: { x: 480, y: 120 },
            data: { label: '文本', kind: 'text', html: 'hello', meta: { error: false } } },
          { id: 'keep1', type: 'pea', position: { x: 120, y: 420 },
            data: { label: '保留位', kind: 'text', html: 'keep', meta: { error: false } } }
        ], [], st.version);
      }"""
    )
    page.wait_for_selector(".react-flow__node[data-id='ai1']", timeout=10000)
    log("[ok] nodes injected: ai1 / t1 / keep1")


def node_count(page):
    return page.evaluate("() => window.__canvas.getState().nodes.length")


def node_exists(page, nid):
    return page.evaluate(f"() => window.__canvas.getState().nodes.some(n => n.id === '{nid}')")


def click_node(page, nid):
    box = page.locator(f".react-flow__node[data-id='{nid}']").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(400)  # 等 NodeChatPrompt 60ms 自动聚焦完成


def main():
    fails = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        register(page)
        enter_canvas(page)
        inject_nodes(page)
        assert node_count(page) == 3

        # ---- 场景1: AI 图节点, 输入栏自动聚焦(空), Delete 应删除节点 ----
        click_node(page, "ai1")
        focused = page.evaluate("() => document.activeElement && document.activeElement.className")
        log(f"[info] focused element after click: {focused}")
        page.keyboard.press("Delete")
        page.wait_for_timeout(300)
        if node_exists(page, "ai1"):
            fails.append("场景1: AI图节点按 Delete 未被删除")
            page.screenshot(path=f"{SHOT}/vdel_fail_ai1.png")
        else:
            log("[PASS] 场景1: AI图节点 Delete 删除成功 (输入栏聚焦态)")

        # ---- 场景2: 文本节点 Delete 删除 ----
        click_node(page, "t1")
        page.keyboard.press("Delete")
        page.wait_for_timeout(300)
        if node_exists(page, "t1"):
            fails.append("场景2: 文本节点按 Delete 未被删除")
        else:
            log("[PASS] 场景2: 文本节点 Delete 删除成功")

        # ---- 场景3: 输入栏有文字时 Delete 不删节点 ----
        click_node(page, "keep1")
        # 在自动聚焦的输入栏里输入文字
        page.keyboard.type("abc")
        page.wait_for_timeout(200)
        page.keyboard.press("Delete")
        page.wait_for_timeout(300)
        if not node_exists(page, "keep1"):
            fails.append("场景3: 输入栏有文字时 Delete 误删了节点")
        else:
            log("[PASS] 场景3: 输入栏有文字时 Delete 不删节点")

        # 清空输入栏文字 (3 次退格删掉 abc)
        for _ in range(3):
            page.keyboard.press("Backspace")
        page.wait_for_timeout(200)
        if not node_exists(page, "keep1"):
            fails.append("场景3b: 退格删文字时误删了节点")
        else:
            log("[PASS] 场景3b: 退格删文字不删节点")

        # ---- 场景4: 空输入栏 Backspace 不删节点 ----
        page.keyboard.press("Backspace")
        page.wait_for_timeout(300)
        if not node_exists(page, "keep1"):
            fails.append("场景4: 空输入栏 Backspace 误删了节点")
        else:
            log("[PASS] 场景4: 空输入栏 Backspace 不删节点 (安全)")

        # ---- 场景4b: 此时(空输入栏)按 Delete 应能删掉 keep1 ----
        page.keyboard.press("Delete")
        page.wait_for_timeout(300)
        if node_exists(page, "keep1"):
            fails.append("场景4b: 空输入栏 Delete 未删除节点")
        else:
            log("[PASS] 场景4b: 空输入栏 Delete 删除节点成功")

        page.screenshot(path=f"{SHOT}/vdel_final.png")
        rel_err = [e for e in errors if "placehold" not in e and "favicon" not in e]
        log(f"[info] console errors: {len(rel_err)}")
        for e in rel_err[:5]:
            log("  " + e[:200])

        browser.close()

    if fails:
        log("\n===== FAIL =====")
        for f in fails:
            log("  ✗ " + f)
        raise SystemExit(1)
    log("\n===== ALL PASS =====")


if __name__ == "__main__":
    main()
