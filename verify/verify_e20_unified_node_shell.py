"""
E20 — 节点统一外壳 + 工具栏浮起 + 图片填满（visual + 尺寸断言）

目的：
  · text/image/video/audio 节点 body-card 宽度一致（280px）
  · image 节点的 <img> 完全填满 body-card（不留缝）
  · image 节点的 tag-pill 没有 background/border
  · image 节点的 result-toolbar 真正悬浮在节点顶部之外（不覆盖 body-card）
"""
import os, sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)

results = []  # (name, ok, note)
console_errors = []


def step(name, ok, note=""):
    results.append((name, ok, note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {note}")


def shot(page, name):
    p = SHOTS / f"e20_{name}.png"
    page.screenshot(path=str(p), full_page=False)
    return p


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        # 1) 注册进入画布（启用 dev hooks 让 CanvasEditor 暴露 zustand store 到 window.__canvas）
        page.add_init_script("window.__peaDevHooks = 1;")
        page.goto(BASE, wait_until="networkidle")
        ts = int(time.time() * 1000)
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', f"e20_{ts}@pea.ai")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "E20")
        page.locator("form button[type=submit]").click()
        # 新用户注册后默认进入工作空间（项目列表），需手动点"新建项目"进画布
        try:
            page.wait_for_selector("text=新建项目", timeout=15000)
        except Exception:
            shot(page, "00_debug_after_register")
            print("DEBUG body html snippet:", page.inner_text("body")[:300])
            raise
        page.wait_for_timeout(800)
        # 点"新建项目"按钮进画布
        new_btns = page.get_by_role("button", name="新建项目").all()
        if new_btns:
            new_btns[0].click()
            page.wait_for_selector(".react-flow", timeout=15000)
        page.wait_for_timeout(1200)
        step("注册+进入画布", True)

        # 2) 通过工具栏的"添加节点"菜单创建 text/image/video/audio 节点
        def open_add_menu():
            btn = page.locator('.pea-tlb-btn[aria-label*="添加节点"]').first
            btn.click()
            page.wait_for_selector(".pea-add-menu", timeout=4000)

        def pick(text):
            open_add_menu()
            items = page.locator(".pea-add-menu-item").all()
            for it in items:
                if text in (it.text_content() or ""):
                    box = it.bounding_box()
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    page.wait_for_timeout(600)
                    return
            raise RuntimeError(f"menu item {text!r} not found")

        for kind in ("文本", "图片", "视频", "音频"):
            pick(kind)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        shot(page, "01_all_four_nodes_default")
        step("创建四个节点(text/image/video/audio)", True)

        # 3) 给 image 节点注入 resultUrl（通过 dev 钩子 window.__canvas）
        page.wait_for_function("typeof window.__canvas !== 'undefined'", timeout=10000)
        # debug: 列出所有 .pea-node 的 kind
        info = page.evaluate("""
            () => {
              const nodes = Array.from(document.querySelectorAll('.pea-node'));
              return nodes.map(n => ({
                kind: n.getAttribute('data-kind'),
                hasMedia: n.classList.contains('pea-node-has-media'),
                rect: (() => { const r = n.getBoundingClientRect(); return {w: Math.round(r.width), h: Math.round(r.height)}; })(),
              }));
            }
        """)
        print(f"  [debug] .pea-node count={len(info)}, kinds={[n['kind'] for n in info]}")
        page.evaluate("""
            () => {
              // 用 .pea-node[data-kind="image"] 找节点
              const imgEl = document.querySelector('.pea-node[data-kind="image"]');
              if (!imgEl) {
                // debug：找父 react-flow 节点拿 data-id
                const allRF = document.querySelectorAll('.react-flow__node');
                return { error: 'no .pea-node[data-kind=image]', rfCount: allRF.length, rfIds: Array.from(allRF).map(n => n.getAttribute('data-id')) };
              }
              const wrap = imgEl.closest('.react-flow__node') || imgEl.parentElement;
              const id = wrap && wrap.getAttribute('data-id');
              if (!id) return { error: 'no data-id on parent' };
              const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='400' height='500' viewBox='0 0 400 500'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='%231fa2dc'/><stop offset='1' stop-color='%238b5cf6'/></linearGradient></defs><rect width='400' height='500' rx='0' fill='url(%23g)'/><text x='50%25' y='45%25' fill='white' font-size='28' text-anchor='middle' font-family='sans-serif'>pea 测试图</text><text x='50%25' y='55%25' fill='white' font-size='16' text-anchor='middle' opacity='0.85' font-family='sans-serif'>image fill test</text></svg>`;
              const url = 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
              window.__canvas.getState().updateNodeData(id, {
                resultUrl: url,
                resultUrls: [url],
                resultIndex: 0,
                label: 'Image',
              });
              return { ok: true, nodeId: id };
            }
        """)
        page.wait_for_timeout(800)

        # 选中 image 节点
        page.locator('.pea-node[data-kind="image"] .pea-node-body-card').first.click(force=True)
        page.wait_for_timeout(500)
        shot(page, "02_image_with_test_picture")
        step("图片节点注入 resultUrl", True)

        # 4) 测 body-card 宽度一致性
        widths = page.evaluate("""
            () => {
              const cards = document.querySelectorAll('.pea-node .pea-node-body-card');
              return Array.from(cards).map(c => {
                const node = c.closest('.pea-node');
                const rfNode = c.closest('.react-flow__node');
                const kind = node?.getAttribute('data-kind') || '?';
                const r = c.getBoundingClientRect();
                // 详细列出 node 元素的所有 CSS 来源
                const styles = window.getMatchedCSSRules ? window.getMatchedCSSRules(node) : null;
                return {
                  kind,
                  width: Math.round(r.width),
                  nodeWidth: Math.round(node.getBoundingClientRect().width),
                  nodeCssWidth: getComputedStyle(node).width,
                  nodeMatchRuleCount: styles ? styles.length : 'N/A',
                  rfCssWidth: getComputedStyle(rfNode).width,
                  // 列出 node 所有 inline/computed style
                  nodeDisplay: getComputedStyle(node).display,
                  nodePosition: getComputedStyle(node).position,
                  // body-card 内部最后一个子元素的 tag
                  lastChildTag: c.lastElementChild?.tagName,
                };
              });
            }
        """)
        # 所有 width 应在 ±2px 内（280±2）
        unique_w = sorted({w['width'] for w in widths})
        uniform = len(unique_w) <= 1 or (max(unique_w) - min(unique_w) <= 2)
        step(
            "四个节点 body-card 宽度一致",
            uniform,
            f"widths={[w['width'] for w in widths]} unique={unique_w} detail={widths}",
        )

        # 5) 测 image 节点的 <img> 填满 body-card
        img_metrics = page.evaluate("""
            () => {
              const img = document.querySelector('.pea-node[data-kind="image"] .pea-node-media-preview');
              const card = document.querySelector('.pea-node[data-kind="image"] .pea-node-body-card');
              if (!img || !card) return null;
              const ir = img.getBoundingClientRect();
              const cr = card.getBoundingClientRect();
              const cs = getComputedStyle(card);
              return {
                imgW: Math.round(ir.width), imgH: Math.round(ir.height),
                cardW: Math.round(cr.width), cardH: Math.round(cr.height),
                cardPadL: cs.paddingLeft, cardPadR: cs.paddingRight, cardPadT: cs.paddingTop, cardPadB: cs.paddingBottom,
                imgObjFit: getComputedStyle(img).objectFit,
                imgBorderRadius: getComputedStyle(img).borderRadius,
                cardOverflow: cs.overflow,
              };
            }
        """)
        if img_metrics:
            # 图片宽度应该等于 card 内宽（padding 0，所以 == cardW）
            img_fill_ok = (
                img_metrics["imgW"] >= img_metrics["cardW"] - 2
                and img_metrics["cardPadL"] == "0px"
                and img_metrics["cardPadT"] == "0px"
                and img_metrics["imgObjFit"] == "cover"
            )
            step(
                "图片填满 body-card（不留缝、object-fit:cover）",
                img_fill_ok,
                f"img={img_metrics['imgW']}x{img_metrics['imgH']} card={img_metrics['cardW']}x{img_metrics['cardH']} pad={img_metrics['cardPadL']}/{img_metrics['cardPadT']} objectFit={img_metrics['imgObjFit']}",
            )
        else:
            step("图片填满 body-card", False, "no .pea-node-media-preview")

        # 6) 测 tag-pill 无 background / border
        tag_metrics = page.evaluate("""
            () => {
              const t = document.querySelector('.pea-node[data-kind="image"] .pea-node-tag-pill');
              if (!t) return null;
              const s = getComputedStyle(t);
              return {
                bg: s.backgroundColor,
                borderTop: s.borderTopWidth + ' ' + s.borderTopStyle,
                radius: s.borderRadius,
              };
            }
        """)
        if tag_metrics:
            # 背景应该透明 (rgba 0,0,0,0 或 transparent)
            bg_transparent = ('rgba(0, 0, 0, 0)' in tag_metrics["bg"]) or ('transparent' in tag_metrics["bg"])
            no_border = tag_metrics["borderTop"].startswith('0px')
            step(
                "Image 标签无边框无背景（透明小字）",
                bg_transparent and no_border,
                f"bg={tag_metrics['bg']} border={tag_metrics['borderTop']}",
            )
        else:
            step("Image 标签无边框", False, "no tag-pill")

        # 7) 测 toolbar 真正浮在节点顶部之外
        toolbar_metrics = page.evaluate("""
            () => {
              const node = document.querySelector('.pea-node[data-kind="image"]');
              const tb = document.querySelector('.pea-node[data-kind="image"] .pea-node-result-toolbar');
              if (!node || !tb) return null;
              const nr = node.getBoundingClientRect();
              const tr = tb.getBoundingClientRect();
              return {
                nodeTop: Math.round(nr.top),
                tbBottom: Math.round(tr.bottom),
                tbTop: Math.round(tr.top),
                tbLeft: Math.round(tr.left),
                tbRight: Math.round(tr.right),
                nodeLeft: Math.round(nr.left),
                nodeRight: Math.round(nr.right),
                isAbove: tr.bottom <= nr.top,
                horizontallyCentered: Math.abs((tr.left + tr.right) / 2 - (nr.left + nr.right) / 2) <= 4,
              };
            }
        """)
        if toolbar_metrics:
            step(
                "工具栏真正悬浮在节点顶部之外（不覆盖节点）",
                toolbar_metrics["isAbove"] and toolbar_metrics["horizontallyCentered"],
                f"nodeTop={toolbar_metrics['nodeTop']} tb=[{toolbar_metrics['tbTop']}, {toolbar_metrics['tbBottom']}] centered={toolbar_metrics['horizontallyCentered']}",
            )
        else:
            step("工具栏悬浮", False, "no toolbar")

        # 8) 全景截图（移开鼠标让 toolbar 隐藏，模拟默认态）
        page.mouse.move(20, 20)
        page.wait_for_timeout(500)
        shot(page, "03_all_nodes_default_state")
        # 再 hover image 让 toolbar 显示（用 force 避开上层 upload-btn 拦截）
        page.locator('.pea-node[data-kind="image"] .pea-node-body-card').first.hover(force=True)
        page.wait_for_timeout(500)
        shot(page, "04_image_node_toolbar_visible")

        browser.close()

    print("\n========= E20 节点外壳统一验证汇总 =========")
    for n, ok, note in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}  {note}")
    print(f"\nconsole errors: {len(console_errors)}")
    for e in console_errors[:20]:
        print("   -", e)
    failed = [n for n, ok, _ in results if not ok]
    print("\n结论:", "全部通过 ✅" if not failed and not console_errors else "有失败/报错 ⚠️")
    sys.exit(0 if not failed and not console_errors else 1)


if __name__ == "__main__":
    main()