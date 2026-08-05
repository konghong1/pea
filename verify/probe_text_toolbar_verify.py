"""
PROBE验证脚本 - 文本节点「边框框」功能条修复回归。

目标：在**真实组件 + 真实 CSS**（probe.html 由 Vite dev server 提供）下，
验证 4 个核心场景 + 全屏弹窗场景，证明「选中但未进编辑态时点格式按钮全部失效」
这一根因已被修复，且不再出现「点工具条/输入栏被踢出编辑态 + 刷闪」。

运行：
  python verify/probe_text_toolbar_verify.py
依赖：managed venv 的 playwright（用系统 Chrome，不下载 chromium）。
"""
import sys
from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "http://localhost:5173/probe.html"

results = []  # (name, ok, detail)


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  -> {detail}" if detail else ""))


def state(page):
    return page.evaluate(
        "() => window.__probe ? {"
        "html: window.__probe.html(),"
        "editing: window.__probe.editing(),"
        "ce: window.__probe.contentEditable(),"
        "flips: window.__probe.classFlips()"
        "} : null"
    )


def has_tag(html, tag):
    return f"<{tag.lower()}" in html.lower()


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

        # ───────────────────────── 场景 A：选中未编辑 → 点 H1（历史 FAIL 用例） ─────────────────────────
        page.evaluate("window.__probe.reset()")
        page.click("#probe-select-only")
        page.wait_for_timeout(120)
        s0 = state(page)
        page.click('button[title="一级标题"]')  # 内联工具条 H1
        page.wait_for_timeout(180)
        s1 = state(page)
        ok_a = has_tag(s1["html"], "h1")
        rec(
            "A: 选中未编辑→点H1 生效",
            ok_a,
            f"ce_before={s0['ce']} -> html_has_h1={ok_a} | html={s1['html'][:60]!r}",
        )

        # ───────────────────────── 场景 B：先进入编辑态 → 点 H1（对照用例，本应 PASS） ─────────────────────────
        page.evaluate("window.__probe.reset()")
        page.click("#probe-edit")  # 单击编辑区进编辑态
        page.wait_for_function("() => window.__probe.editing() === true", timeout=5000)
        page.click('button[title="粗体 (Ctrl+B)"]')
        page.wait_for_timeout(150)
        s2 = state(page)
        ok_b = "<b>" in s2["html"].lower() or "<strong>" in s2["html"].lower()
        rec("B: 编辑态→点粗体 生效", ok_b, f"html_has_bold={ok_b} | html={s2['html'][:60]!r}")

        # ───────────────────────── 场景 C：编辑态 → 点下方输入栏按钮 → 不应被踢出编辑态（刷闪根因） ─────────────────────────
        page.evaluate("window.__probe.reset()")
        page.click("#probe-edit")
        page.wait_for_function("() => window.__probe.editing() === true", timeout=5000)
        page.evaluate("window.__probe.reset()")  # 进入编辑态后的迁移抖动先清零
        page.click("#probe-mic")  # 下方输入栏的按钮
        page.wait_for_timeout(150)
        s3 = state(page)
        ok_c = s3["editing"] is True and s3["flips"] <= 2
        rec(
            "C: 编辑态→点输入栏 不丢编辑态/不刷闪",
            ok_c,
            f"editing={s3['editing']} flips={s3['flips']}",
        )

        # ───────────────────────── 场景 D：点过输入栏后 → 再点 H1 仍应生效 ─────────────────────────
        page.click('button[title="一级标题"]')
        page.wait_for_timeout(180)
        s4 = state(page)
        ok_d = has_tag(s4["html"], "h1")
        rec("D: 点输入栏后→点H1 仍生效", ok_d, f"html_has_h1={ok_d} | html={s4['html'][:60]!r}")

        # ───────────────────────── 场景 E：双击弹窗 → 字符数非0 + 点 H1 生效 ─────────────────────────
        page.click("#probe-open-modal")
        page.wait_for_selector(".tne-editor-content", timeout=8000)
        page.wait_for_timeout(200)
        char_txt = ""
        try:
            char_txt = page.locator("text=/\\d+\\s*字符/").first.inner_text(timeout=4000)
        except Exception as e:
            char_txt = f"<未找到字符数: {e}>"
        try:
            page.click('button.tne-tool-btn[title^="一级标题"]')  # 弹窗内 H1
        except Exception as e:
            rec("E: 弹窗内点H1", False, f"点击失败: {e}")
            char_txt += " | H1点击异常"
        page.wait_for_timeout(180)
        modal_html = page.eval_on_selector(".tne-editor-content", "el => el.innerHTML")
        ok_e_html = has_tag(modal_html, "h1")
        ok_e_char = ("字符" in char_txt) and not char_txt.strip().startswith("0")
        rec(
            "E: 弹窗 字符数非0",
            ok_e_char,
            f"char='{char_txt}'",
        )
        rec("E: 弹窗内点H1 生效", ok_e_html, f"modal_html_has_h1={ok_e_html}")

        # ───────────────────────── 运行期错误检查 ─────────────────────────
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
