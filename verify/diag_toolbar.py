# -*- coding: utf-8 -*-
"""诊断：image 节点功能条是否被 body-card 的 overflow:hidden 裁掉。"""
from __future__ import annotations
from playwright.sync_api import sync_playwright

WEB = "http://localhost:8088"
SVG_DATA_URL = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'>"
    "<rect width='200' height='200' fill='%231fa2dc'/>"
    "<circle cx='100' cy='100' r='60' fill='white'/>"
    "</svg>"
)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        page = ctx.new_page()
        page.goto(WEB, wait_until="networkidle")

        ts = page.evaluate("Date.now()")
        email = f"diag_{ts}@pea.ai"
        if page.locator("text=去注册").count() > 0:
            page.locator("text=去注册").first.click()
            page.wait_for_timeout(500)
        all_inputs = page.locator("input:visible")
        cnt = all_inputs.count()
        if cnt >= 2:
            all_inputs.nth(0).fill(email)
            all_inputs.nth(1).fill("test1234")
            if cnt >= 3:
                all_inputs.nth(2).fill("Diag")
        page.locator("button", has_text="注").first.click()
        page.wait_for_timeout(1500)

        page.wait_for_selector("text=新建项目", timeout=8000)
        page.locator("text=新建项目").first.click()
        page.wait_for_timeout(800)
        page.wait_for_selector(".react-flow", timeout=10000)
        page.wait_for_timeout(400)

        def add_node(label):
            page.locator(".pea-tlb-btn[aria-label*='添加节点']").first.click()
            page.wait_for_timeout(250)
            page.locator(f".pea-add-menu-item:has-text('{label}')").first.click()
            page.wait_for_timeout(350)

        add_node("图片")
        page.wait_for_timeout(300)

        ok_inject = page.evaluate(
            """(url) => {
              const api = window.__canvas; if (!api) return false;
              const st = api.getState();
              const img = st.nodes.find(n => n.data.kind === 'image'); if (!img) return false;
              st.updateNodeData(img.id, { resultUrl: url, resultUrls: [url], resultIndex: 0 });
              return true;
            }""",
            SVG_DATA_URL,
        )
        print("inject:", ok_inject)
        page.wait_for_timeout(400)

        img_node = page.locator('.pea-node[data-kind="image"]').first
        img_node.scroll_into_view_if_needed()
        page.wait_for_timeout(300)

        # 悬停节点以触发 toolbar 显示
        img_node.hover(force=True)
        page.wait_for_timeout(400)

        info = img_node.evaluate(
            """() => {
              const node = document.querySelector('.pea-node[data-kind="image"]');
              const tb = node.querySelector('.pea-node-result-toolbar');
              const card = node.querySelector('.pea-node-body-card');
              const wrap = node.querySelector('.pea-node-result-image-wrap');
              const r = (el) => { const b = el.getBoundingClientRect(); return {x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), bottom: Math.round(b.bottom), top: Math.round(b.y)}; };
              return {
                hasToolbar: !!tb,
                toolbar: tb ? r(tb) : null,
                card: card ? r(card) : null,
                wrap: wrap ? {overflow: getComputedStyle(wrap).overflow, br: getComputedStyle(wrap).borderRadius} : null,
                cardOverflow: card ? getComputedStyle(card).overflow : null,
                cardBr: card ? getComputedStyle(card).borderRadius : null,
                tbOpacity: tb ? getComputedStyle(tb).opacity : null,
              };
            }"""
        )
        print("INFO:", info)

        # 截图（悬停态）
        page.screenshot(path="verify/shots/diag_toolbar_hover.png")
        print("screenshot saved: verify/shots/diag_toolbar_hover.png")

        browser.close()


if __name__ == "__main__":
    main()
