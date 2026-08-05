# -*- coding: utf-8 -*-
"""
文本节点「双击全屏编辑弹窗」(TextNodeEditorModal) 回归。

对应用户反馈问题①：
  «双击文本节点时，点击上面编辑功能（如一级标题）没作用»
  «输入后还是没有作用»
  «第一次双击进去后下方的字符数是 0»
  «点击上方功能时，编辑框和上方功能条会闪动»

在真实 antd Modal + 真实 CSS 下验证，不依赖后端。

用法： python verify/probe_modal_toolbar.py
"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173/probe.html"

CASES = [
    ("一级标题 (Ctrl+Alt+1)", ["<h1"]),
    ("二级标题 (Ctrl+Alt+2)", ["<h2"]),
    ("三级标题 (Ctrl+Alt+3)", ["<h3"]),
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
    ("橙色", ["f39c12", "rgb(243, 156, 18)"]),
]

EDITOR = ".tne-editor-content"


def open_modal(page):
    page.goto(URL, wait_until="networkidle", timeout=30000)
    page.wait_for_selector("#probe-open-modal", timeout=10000)
    page.click("#probe-open-modal")
    page.wait_for_selector(EDITOR, timeout=8000)
    page.wait_for_timeout(350)  # 等 setEditorRef 的 rAF focus 完成


def main():
    rows = []
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 950})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        # ── 前置检查：字符数是否为 0（用户反馈的第三个现象）──────────
        open_modal(page)
        footer_text = page.locator("text=/\\d+ 字符/").first.inner_text()
        editor_html = page.eval_on_selector(EDITOR, "e => e.innerHTML")
        active_cls = page.evaluate("() => document.activeElement?.className || ''")
        char_ok = not footer_text.strip().startswith("0 ")
        print(f"[初始] 字符数= {footer_text!r}  编辑区内容={editor_html[:40]!r}")
        print(f"[初始] activeElement.class={active_cls!r}  -> {'OK' if char_ok else 'FAIL(字符数为0)'}")
        ok = ok and char_ok

        # ── 逐个按钮 ─────────────────────────────────────────────
        for title, expects in CASES:
            open_modal(page)
            # 全选编辑区内容，模拟用户「选中文字后点格式」
            page.eval_on_selector(
                EDITOR,
                """e => {
                    e.focus();
                    const r = document.createRange();
                    r.selectNodeContents(e);
                    const s = getSelection();
                    s.removeAllRanges();
                    s.addRange(r);
                }""",
            )
            page.wait_for_timeout(80)
            btn = page.locator(f'.tne-toolbar button[title="{title}"]')
            btn.wait_for(state="visible", timeout=5000)
            btn.click()
            page.wait_for_timeout(200)

            html = page.eval_on_selector(EDITOR, "e => e.innerHTML").lower()
            preview = page.eval_on_selector(".tne-preview-content", "e => e.innerHTML").lower()
            hit = any(x.lower() in html for x in expects)
            prev_sync = any(x.lower() in preview for x in expects)
            ok = ok and hit
            rows.append((title, "OK" if hit else "FAIL", "OK" if prev_sync else "-", html[:56]))

        browser.close()

    w = max(len(r[0]) for r in rows) + 2
    print("=" * 100)
    print(f"{'按钮'.ljust(w)}{'编辑区':<8}{'预览同步':<10}innerHTML 摘要")
    print("-" * 100)
    for t, r, pv, h in rows:
        print(f"{t.ljust(w)}{r:<8}{pv:<10}{h}")
    print("-" * 100)
    print("pageerrors:", errors)
    print("OVERALL:", "PASS" if ok and not errors else "FAIL")
    return 0 if (ok and not errors) else 1


if __name__ == "__main__":
    sys.exit(main())
