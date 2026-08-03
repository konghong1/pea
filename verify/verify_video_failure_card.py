"""E2E 验证：视频生成失败时节点内失败卡片不显示「当时提示词」区域，
只显示失败信息（标题/提示/操作按钮），无论用户是否输入过 editorText。"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = "http://localhost:5173"
EMAIL = "test@example.com"
PASSWORD = "password123"
OUT = Path(__file__).resolve().parent / "verify"
OUT.mkdir(exist_ok=True)


def nav_to_canvas(page):
    if "/canvas" not in page.url:
        try:
            page.locator("text=未命名画布").first.click(timeout=6000)
        except Exception:
            page.locator("a[href*='/canvas']").first.click(timeout=6000)
    page.wait_for_selector(".react-flow__pane", timeout=30000)
    time.sleep(1)


def inspect_failure_card(page, vid):
    return page.evaluate(
        """(vid) => {
            const node = document.querySelector(`.react-flow__node[data-id="${vid}"]`);
            const failure = node?.querySelector('.pea-node-failure');
            const promptSection = failure?.querySelector('.pea-node-failure-prompt');
            const title = failure?.querySelector('.pea-node-failure-title')?.textContent || '';
            const hint = failure?.querySelector('.pea-node-failure-hint')?.textContent || '';
            const actions = failure?.querySelector('.pea-node-failure-actions');
            return {
                hasFailure: !!failure,
                hasPromptSection: !!promptSection,
                title,
                hint,
                hasActions: !!actions,
            };
        }""",
        vid,
    )


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(f"{WEB}/login")
        page.fill("input#email, input[type='email']", EMAIL)
        page.fill("input#password, input[type='password']", PASSWORD)
        page.click("button:has-text('登 录')")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        if "/login" in page.url:
            raise RuntimeError("login failed")
        nav_to_canvas(page)

        # 添加一个 video 节点
        vid = page.evaluate("""() => {
            const s = window.__canvas.getState();
            return s.addNode({ kind: 'video', label: '视频', prompt: '', meta: {} }, { x: 400, y: 300 });
        }""")
        time.sleep(0.5)

        # 场景 1：editorText 为空，prompt 是机器拼接的含参考图清单的字符串
        machine_prompt = "【参考图清单】共 2 张，已随请求按序上传，请严格按编号分别使用：\n" \
                         "【参考图 1】包包：请准确识别图中物体的款式、颜色、材质、形状、图案与细节；" \
                         "在生成时根据用户指令将该物体作为素材融入画面，保持其外观特征一致性。\n" \
                         "【参考图 2】人物：...\n\n模特手持包包走在巴黎街头..."
        page.evaluate(
            """([vid, machine_prompt]) => {
                window.__canvas.getState().updateNodeData(vid, {
                    error: 'submit error: video HTTP 520: upstream timeout',
                    prompt: machine_prompt,
                    meta: {},
                    generating: false,
                    resultUrl: undefined,
                    resultUrls: undefined,
                }, false);
            }""",
            [vid, machine_prompt],
        )
        time.sleep(0.5)
        page.screenshot(path=str(OUT / "failure_no_editor_text.png"))

        result = inspect_failure_card(page, vid)
        print(f"[no editorText] {result}")
        assert result["hasFailure"], "失败卡未渲染"
        assert not result["hasPromptSection"], "editorText 为空时不应显示「当时提示词」区域"
        assert result["hasActions"], "应保留操作按钮"

        # 场景 2：设置 editorText，仍然不应显示「当时提示词」区域
        page.evaluate(
            """(vid) => {
                window.__canvas.getState().updateNodeData(vid, {
                    meta: { editorText: '<p>一个模特在街头展示包包，背景是巴黎黄昏</p>' },
                }, false);
            }""",
            vid,
        )
        time.sleep(0.5)
        page.screenshot(path=str(OUT / "failure_with_editor_text.png"))
        result2 = inspect_failure_card(page, vid)
        print(f"[with editorText] {result2}")
        assert not result2["hasPromptSection"], "有 editorText 时也不应显示「当时提示词」区域"
        assert result2["hasActions"], "应保留操作按钮"

        browser.close()
        print("PASS: failure card never shows prompt section")


if __name__ == "__main__":
    main()
