# -*- coding: utf-8 -*-
"""
文本节点「边框框」功能条 —— 全按钮回归。

用户原话是「这个边框框功能**全部**不能使用」，所以逐个点完 17 个按钮，
每个都在最恶劣的路径下验证：
  选中节点但**不进入编辑态** → 点按钮 → 断言 DOM 真的发生了预期变化。

用法： python verify/probe_text_toolbar_all.py
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173/probe.html"

# (按钮 title, 期望在 innerHTML 中出现的片段之一)
CASES = [
    ("一级标题", ["<h1"]),
    ("二级标题", ["<h2"]),
    ("三级标题", ["<h3"]),
    ("正文段落", ["<p"]),
    ("粗体 (Ctrl+B)", ["<b", "<strong", "font-weight"]),
    ("斜体 (Ctrl+I)", ["<i", "<em", "font-style"]),
    ("下划线 (Ctrl+U)", ["<u", "underline"]),
    ("删除线", ["<strike", "<s>", "line-through"]),
    ("无序列表", ["<ul"]),
    ("有序列表", ["<ol"]),
    ("引用块", ["<blockquote"]),
    ("行内代码", ["<pre"]),
    ("分割线", ["<hr"]),
    ("蓝色", ["1fa2dc", "rgb(31, 162, 220)"]),
    ("红色", ["e74c3c", "rgb(231, 76, 60)"]),
    ("绿色", ["27ae60", "rgb(39, 174, 96)"]),
    ("橙色/警告", ["f39c12", "rgb(243, 156, 18)"]),
]


def main():
    rows = []
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        for title, expects in CASES:
            # 每个按钮都从干净状态开始，走「仅选中、未进编辑态」这条最恶劣路径
            page.goto(URL, wait_until="networkidle", timeout=30000)
            page.wait_for_selector("#probe-edit", timeout=10000)
            page.wait_for_timeout(150)
            page.click("#probe-select-only")
            page.wait_for_timeout(120)
            page.evaluate("window.__probe.reset()")

            btn = page.locator(f'.tnt-bar button[title="{title}"]')
            btn.wait_for(state="visible", timeout=5000)
            btn.click()
            page.wait_for_timeout(160)

            html = page.evaluate("window.__probe.html()").lower()
            flips = page.evaluate("window.__probe.classFlips()")
            hit = any(x.lower() in html for x in expects)
            ok = ok and hit
            rows.append((title, "OK" if hit else "FAIL", flips, html[:64]))

        browser.close()

    w = max(len(r[0]) for r in rows) + 2
    print("=" * 96)
    print(f"{'按钮'.ljust(w)}{'结果':<8}{'抖动':<6}innerHTML 摘要")
    print("-" * 96)
    for t, r, f, h in rows:
        print(f"{t.ljust(w)}{r:<8}{f:<6}{h}")
    print("-" * 96)
    print("pageerrors:", errors)
    print("OVERALL:", "PASS" if ok and not errors else "FAIL")
    return 0 if (ok and not errors) else 1


if __name__ == "__main__":
    sys.exit(main())
