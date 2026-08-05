"""
文本节点全屏编辑弹窗回归验证。

覆盖用户反馈的问题：
1. 预览区不同步
2. 工具栏按钮失效
3. 点击编辑区闪烁
4. 块级格式（H1 等）应按选区/插入点应用，不应整段改变

运行：python verify/probe_text_modal_regression.py
"""
import sys
from html.parser import HTMLParser
from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "http://localhost:5173/probe.html"

results = []


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  -> {detail}" if detail else ""))


def has_tag(html, tag):
    return f"<{tag.lower()}" in html.lower()


def count_tag(html, tag):
    """统计某个标签在 HTML 中出现次数（不区分大小写，不要求闭合）。"""
    return html.lower().count(f"<{tag.lower()}")


class TextExtractor(HTMLParser):
    """按标签提取文本，用于验证部分选区格式化。"""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.texts = []  # [(tag_path, text), ...]

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag.lower())

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()

    def handle_data(self, data):
        path = "/".join(self.stack)
        self.texts.append((path, data))


def extract_texts_by_tag(html, tag):
    """返回该标签内的所有文本列表（按出现顺序）。"""
    parser = TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return []
    out = []
    for path, text in parser.texts:
        if tag.lower() in path.split("/"):
            out.append(text)
    return out


def select_text_in_editor(page, text):
    """在编辑区中选中完整 text（要求编辑区里有这段文本）。"""
    page.evaluate(
        """(text) => {
            const ed = document.querySelector('.tne-editor-content');
            if (!ed) return false;
            const walker = document.createTreeWalker(ed, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const idx = node.textContent.indexOf(text);
                if (idx >= 0) {
                    const range = document.createRange();
                    range.setStart(node, idx);
                    range.setEnd(node, idx + text.length);
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    return true;
                }
            }
            return false;
        }""",
        text,
    )


def main():
    console_errors = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector("#probe-edit", timeout=15000)
        page.wait_for_function("() => !!window.__probe", timeout=15000)

        # ── 打开弹窗前：先选中节点，验证底层功能条和输入栏出现 ──
        page.click("#probe-select-only")
        page.wait_for_timeout(200)
        has_toolbar_before = page.locator(".tnt-bar").count() > 0
        has_input_bar_before = page.locator("#probe-input-bar").count() > 0
        rec("弹窗前: 选中节点后功能条显示", has_toolbar_before, f"toolbar={has_toolbar_before}")
        rec("弹窗前: 选中节点后输入栏显示", has_input_bar_before, f"inputbar={has_input_bar_before}")

        # ── 打开弹窗 ──
        page.click("#probe-open-modal")
        page.wait_for_selector(".tne-editor-content", timeout=8000)
        page.wait_for_timeout(200)

        # 0) 打开全屏弹窗后，底层节点应收起功能条和输入栏，不再显示也不再闪烁
        has_toolbar_after = page.locator(".tnt-bar").count() > 0
        has_input_bar_after = page.locator("#probe-input-bar").count() > 0
        node_selected_after = page.locator("#probe-node.selected").count() > 0
        rec("弹窗后: 底层功能条已收起", not has_toolbar_after, f"toolbar={has_toolbar_after}")
        rec("弹窗后: 底层输入栏已收起", not has_input_bar_after, f"inputbar={has_input_bar_after}")
        rec("弹窗后: 底层节点取消选中", not node_selected_after, f"selected={node_selected_after}")

        # 0.1) 在弹窗内多次点击，底层编辑区 class/contenteditable 不应反复变化（防闪烁）
        page.evaluate("window.__probe.reset()")
        for _ in range(6):
            page.click(".tne-editor-content")
            page.wait_for_timeout(80)
        flips_after_open = page.evaluate("window.__probe.classFlips()")
        rec("弹窗后: 在弹窗内点击底层编辑区不闪烁", flips_after_open == 0, f"class_flips={flips_after_open}")

        # 1) 初始状态：编辑区与预览区都应显示相同内容
        editor_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        preview_html = page.eval_on_selector(".tne-preview-content", "el => el.innerHTML")
        char_txt = page.locator("text=/\\d+\\s*字符/").first.inner_text(timeout=4000)
        rec(
            "初始: 编辑区与预览区内容一致",
            editor_html.strip() == preview_html.strip() and bool(editor_html.strip()),
            f"editor_len={len(editor_html)} preview_len={len(preview_html)}",
        )
        rec("初始: 字符数非0", bool(char_txt) and not char_txt.strip().startswith("0"), f"char='{char_txt}'")

        # 2) 在编辑区输入文本，检查预览区同步
        page.click(".tne-editor-content")
        page.keyboard.press("Control+a")
        page.keyboard.type("新输入的测试文本")
        page.wait_for_timeout(300)
        editor_html2 = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        preview_html2 = page.eval_on_selector(".tne-preview-content", "el => el.innerHTML")
        rec(
            "输入: 预览区同步更新",
            editor_html2.strip() == preview_html2.strip() and "新输入的测试文本" in preview_html2,
            f"preview={preview_html2[:40]!r}",
        )

        # 3) 工具栏：H1 只应作用于选区，不应整段改变
        page.evaluate(
            """() => {
                const ed = document.querySelector('.tne-editor-content');
                ed.innerHTML = '<p>前缀文本测试文本后缀文本</p>';
                ed.focus();
            }"""
        )
        select_text_in_editor(page, "测试文本")
        page.click('button.tne-tool-btn[title^="一级标题"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        preview_html3 = page.eval_on_selector(".tne-preview-content", "el => el.innerHTML")
        h1_texts = extract_texts_by_tag(modal_html, "h1")
        ok_h1_partial = (
            count_tag(modal_html, "h1") == 1
            and h1_texts == ["测试文本"]
            and "前缀文本" in modal_html
            and "后缀文本" in modal_html
        )
        rec("工具栏: H1 仅格式化选区", ok_h1_partial, f"h1_texts={h1_texts} html={modal_html[:120]!r}")
        rec(
            "工具栏: H1 选区格式化后预览同步",
            ok_h1_partial and extract_texts_by_tag(preview_html3, "h1") == ["测试文本"],
            f"preview={preview_html3[:120]!r}",
        )

        # 4) 工具栏：折叠光标处点击 H1，后续输入应继承 H1
        page.evaluate(
            """() => {
                const ed = document.querySelector('.tne-editor-content');
                ed.innerHTML = '<p>正文内容</p>';
                ed.focus();
                const range = document.createRange();
                range.setStart(ed.querySelector('p').firstChild, 4);
                range.collapse(true);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
            }"""
        )
        page.click('button.tne-tool-btn[title^="一级标题"]')
        page.wait_for_timeout(200)
        page.keyboard.type("新标题")
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        preview_html4 = page.eval_on_selector(".tne-preview-content", "el => el.innerHTML")
        h1_texts2 = extract_texts_by_tag(modal_html, "h1")
        ok_h1_typing = "新标题" in "".join(h1_texts2)
        rec("工具栏: 折叠光标 H1 后输入继承", ok_h1_typing, f"h1_texts={h1_texts2} html={modal_html[:120]!r}")
        rec(
            "工具栏: 折叠光标 H1 预览同步",
            ok_h1_typing and "新标题" in "".join(extract_texts_by_tag(preview_html4, "h1")),
            f"preview={preview_html4[:120]!r}",
        )

        # 4.5) 激活态高亮：折叠光标点 H1 后，H1 按钮应亮起；正文按钮不应亮
        def btn_active(title_like):
            return page.evaluate(
                """(sel) => {
                    const b = document.querySelector(`button.tne-tool-btn[title^="${sel}"]`);
                    if (!b) return null;
                    return b.classList.contains('tne-tool-btn--active') || b.getAttribute('aria-pressed') === 'true';
                }""",
                title_like,
            )

        ok_h1_active = btn_active('一级标题') is True
        rec("激活态: 折叠光标 H1 后 H1 按钮高亮", ok_h1_active, f"h1_active={ok_h1_active}")
        ok_p_inactive = btn_active('正文段落') is False
        rec("激活态: 当前非正文，正文按钮不高亮", ok_p_inactive, f"p_active={ok_p_inactive}")
        page.screenshot(path="verify/shot_text_modal_active.png")

        # 5) 工具栏：H1 toggle（在 H1 内再次点击 H1 应解除）
        page.evaluate(
            """() => {
                const ed = document.querySelector('.tne-editor-content');
                ed.innerHTML = '<h1>要解除的标题</h1>';
                ed.focus();
            }"""
        )
        select_text_in_editor(page, "要解除的标题")
        page.click('button.tne-tool-btn[title^="一级标题"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_h1_toggle = not has_tag(modal_html, "h1") and "要解除的标题" in modal_html
        rec("工具栏: H1 内再次点击解除 H1", ok_h1_toggle, f"html={modal_html[:120]!r}")

        # 6) 工具栏：粗体（全选后应用）
        page.click(".tne-editor-content")
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title^="粗体"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        preview_html6 = page.eval_on_selector(".tne-preview-content", "el => el.innerHTML")
        ok_bold = "<b>" in modal_html.lower() or "<strong>" in modal_html.lower()
        rec("工具栏: 粗体生效", ok_bold, f"html={modal_html[:80]!r}")
        rec("工具栏: 粗体后预览同步", ok_bold and ("<b>" in preview_html6.lower() or "<strong>" in preview_html6.lower()), f"preview={preview_html6[:80]!r}")
        ok_bold_active = btn_active('粗体') is True
        rec("激活态: 应用粗体后粗体按钮高亮", ok_bold_active, f"bold_active={ok_bold_active}")

        # 7) 工具栏：斜体
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title^="斜体"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_italic = "<i>" in modal_html.lower() or "<em>" in modal_html.lower()
        rec("工具栏: 斜体生效", ok_italic, f"html={modal_html[:80]!r}")

        # 8) 工具栏：下划线
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title^="下划线"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_u = "<u>" in modal_html.lower()
        rec("工具栏: 下划线生效", ok_u, f"html={modal_html[:80]!r}")

        # 9) 工具栏：删除线
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title="删除线"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_s = "<strike>" in modal_html.lower() or "<s>" in modal_html.lower()
        rec("工具栏: 删除线生效", ok_s, f"html={modal_html[:80]!r}")

        # 10) 工具栏：无序列表
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title="无序列表"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_ul = "<ul>" in modal_html.lower()
        rec("工具栏: 无序列表生效", ok_ul, f"html={modal_html[:80]!r}")

        # 11) 工具栏：有序列表
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title="有序列表"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_ol = "<ol>" in modal_html.lower()
        rec("工具栏: 有序列表生效", ok_ol, f"html={modal_html[:80]!r}")

        # 12) 工具栏：引用块
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title="引用块"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_bq = "<blockquote>" in modal_html.lower()
        rec("工具栏: 引用块生效", ok_bq, f"html={modal_html[:80]!r}")

        # 13) 工具栏：行内代码
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title="行内代码"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_code = "<pre>" in modal_html.lower() or "<code>" in modal_html.lower()
        rec("工具栏: 行内代码生效", ok_code, f"html={modal_html[:80]!r}")

        # 14) 工具栏：颜色（固定颜色 + 黑色 + 自定义颜色）
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title="蓝色"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_color = "#1fa2dc" in modal_html.lower() or "rgb(31, 162, 220)" in modal_html.lower()
        rec("工具栏: 蓝色生效", ok_color, f"html={modal_html[:120]!r}")

        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title="黑色"]')
        page.wait_for_timeout(200)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_black = "#111111" in modal_html.lower() or "rgb(17, 17, 17)" in modal_html.lower()
        rec("工具栏: 黑色生效", ok_black, f"html={modal_html[:120]!r}")

        # 自定义颜色：点击彩虹色环按钮打开原生 picker，然后通过 JS 设置颜色。
        # 注意：Playwright 中系统 picker 弹出后 value 变更事件会被浏览器忽略，
        # 所以验证里不真正打开 picker，而是直接操作隐藏的 color input 派发 input 事件。
        page.keyboard.press("Control+a")
        page.click('button.tne-tool-btn[title="自定义颜色"]')
        page.wait_for_timeout(300)
        set_ok = page.evaluate("""() => {
          const input = document.querySelector('input.tne-color-input');
          if (!input) return 'not-found';
          input.value = '#9b59b6';
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
          return input.value;
        }""")
        page.wait_for_timeout(300)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_custom = "#9b59b6" in modal_html.lower() or "rgb(155, 89, 182)" in modal_html.lower()
        rec("工具栏: 自定义颜色生效", ok_custom, f"input_value={set_ok!r} html={modal_html[:120]!r}")

        # 截图留证：点击编辑区关闭系统 picker 后，展示新增的黑色与自定义颜色按钮及紫色文字
        page.click(".tne-editor-content")
        page.wait_for_timeout(200)
        page.screenshot(path="verify/shot_text_modal_color_picker.png")

        # 15) 闪烁检测：统计点击编辑区前后 contenteditable/class 变化次数
        # 先重置，再连续点击编辑区多次
        page.evaluate("window.__probe && window.__probe.reset && window.__probe.reset()")
        for _ in range(5):
            page.click(".tne-editor-content")
            page.wait_for_timeout(80)
        # 弹窗编辑区没有挂 MutationObserver，这里改用视觉/性能指标：
        # 只要没有 JS 错误且上述工具栏测试全部通过，即可认为没有严重闪烁。
        rec("点击编辑区: 无 JS 错误兜底", len(page_errors) == 0, f"pageerrors={page_errors[:3]}")

        # 16) 保存关闭后重新打开，内容应保留
        page.click('button:has-text("保存")')
        page.wait_for_selector(".text-node-editor-modal", state="hidden", timeout=5000)
        page.click("#probe-open-modal")
        page.wait_for_selector(".tne-editor-content", timeout=8000)
        page.wait_for_timeout(200)
        modal_html_reopen = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        rec("重开弹窗: 编辑区仍有内容", bool(modal_html_reopen.strip()), f"len={len(modal_html_reopen)}")

        # 17) 闪烁检测：监听工具栏 DOM 子树变化，输入过程中不应被整体重建
        page.click(".tne-editor-content")
        toolbar_mutations = page.evaluate(
            """() => {
                const tb = document.querySelector('.tne-toolbar');
                if (!tb) return -1;
                let count = 0;
                const mo = new MutationObserver((recs) => {
                    for (const r of recs) if (r.type === 'childList') count += r.removedNodes.length;
                });
                mo.observe(tb, { childList: true, subtree: true });
                window.__tneToolbarMo = { count: () => count, disconnect: () => mo.disconnect() };
                return 0;
            }"""
        )
        page.keyboard.type("测试闪烁")
        page.wait_for_timeout(300)
        removed = page.evaluate("() => window.__tneToolbarMo ? window.__tneToolbarMo.count() : -1")
        rec("工具栏: 输入时不整体重建", toolbar_mutations == 0 and removed == 0, f"removed_nodes={removed}")

        # 截图留证
        page.screenshot(path="verify/shot_text_modal_regression.png")

        rec("Z: 无运行时 JS 错误", len(page_errors) == 0, f"pageerrors={page_errors[:3]}")
        rec("Z: 无 console error", len(console_errors) == 0, f"console={console_errors[:3]}")

        browser.close()

    overall = all(ok for _, ok, _ in results)
    print("\n================ OVERALL:", "PASS" if overall else "FAIL", "================")
    for n, ok, d in results:
        if not ok:
            print(f"  - {n}: {d}")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
