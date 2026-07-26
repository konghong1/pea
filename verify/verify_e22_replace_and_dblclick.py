# -*- coding: utf-8 -*-
"""E22：图片右上角「替换」按钮 + 单击 vs 双击编辑修复

  1) 替换按钮：image 节点有图（result 或 uploaded）时，hover/选中后右上角出现「替换」胶囊
     点击触发 file input（替换 = 设新的 data.url，清掉旧 result/savedToLibrary）。
  2) 单击 vs 双击编辑：text 节点单击只选中（contentEditable=false、placeholder 显示），
     双击进入编辑态（contentEditable=true、is-editing 视觉描边、聚焦）。
     image/video/audio 节点双击不响应（editing 仍为 false，contentEditable=false）。
"""
from __future__ import annotations
import pathlib
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
    errors: list[str] = []
    console_errors: list[str] = []

    def step(label, ok, detail=""):
        if ok:
            print(f"[PASS] {label}  {detail}")
        else:
            errors.append(label)
            print(f"[FAIL] {label}  {detail}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        # 在所有页面脚本运行前注入 __peaDevHooks=1，让 prod 构建也暴露 __canvas
        ctx.add_init_script("window.__peaDevHooks = 1;")
        page = ctx.new_page()
        page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))

        page.goto(WEB, wait_until="networkidle")

        # 注册 / 进入项目 / 进入画布
        ts = page.evaluate("Date.now()")
        email = f"e22_{ts}@pea.ai"
        # 登录页：先点"去注册"链接触发注册表单
        if page.locator("text=去注册").count() > 0:
            page.locator("text=去注册").first.click()
            page.wait_for_timeout(500)
        # 注册表单有 3 个输入：邮箱 / 密码 / 昵称
        all_inputs = page.locator("input:visible")
        cnt = all_inputs.count()
        if cnt >= 2:
            all_inputs.nth(0).fill(email)
            page.wait_for_timeout(150)
            all_inputs.nth(1).fill("test1234")
            page.wait_for_timeout(150)
            if cnt >= 3:
                all_inputs.nth(2).fill("E22")
        # 注册按钮
        page.locator("button", has_text="注").first.click()
        page.wait_for_timeout(1500)

        # 项目列表 → 新建项目（点一次即创建并打开画布）
        page.wait_for_selector("text=新建项目", timeout=8000)
        page.locator("text=新建项目").first.click()
        page.wait_for_timeout(800)

        page.wait_for_selector(".react-flow", timeout=10000)
        page.wait_for_timeout(400)
        step("进入画布", page.locator(".react-flow").count() == 1)

        # 建 3 个节点：text / image / video
        def add_node(label):
            page.locator(".pea-tlb-btn[aria-label*='添加节点']").first.click()
            page.wait_for_timeout(250)
            page.locator(f".pea-add-menu-item:has-text('{label}')").first.click()
            page.wait_for_timeout(350)

        add_node("文本")
        add_node("图片")
        add_node("视频")
        page.wait_for_timeout(300)

        n_text = page.locator('.pea-node[data-kind="text"]').count()
        n_image = page.locator('.pea-node[data-kind="image"]').count()
        n_video = page.locator('.pea-node[data-kind="video"]').count()
        step("创建 3 个节点 (text/image/video)", n_text == 1 and n_image == 1 and n_video == 1,
             f"text={n_text} image={n_image} video={n_video}")

        # 注入 resultUrl 到 image 节点
        ok_inject = page.evaluate(
            """(url) => {
              const api = window.__canvas;
              if (!api) return false;
              const st = api.getState();
              const img = st.nodes.find(n => n.data.kind === 'image');
              if (!img) return false;
              st.updateNodeData(img.id, { resultUrl: url, resultUrls: [url], resultIndex: 0 });
              return true;
            }""",
            SVG_DATA_URL,
        )
        step("注入 resultUrl 到 image 节点", ok_inject is True)
        page.wait_for_timeout(400)

        # === 检查 1：替换按钮存在并默认可见 ===
        img_node = page.locator('.pea-node[data-kind="image"]').first
        replace_btn = img_node.locator(".pea-node-result-replace")
        step("image 节点有「替换」按钮", replace_btn.count() == 1,
             f"replace_btns={replace_btn.count()}")

        # image 节点上替换按钮默认可见（无需 hover）
        op = img_node.locator(".pea-node-result-replace").evaluate(
            "el => getComputedStyle(el).opacity"
        )
        step("替换按钮默认可见 (opacity=1)", float(op) > 0.9, f"opacity={op}")

        # 点击替换按钮不应抛错（file input 应触发）
        try:
            replace_btn.first.click(force=True, no_wait_after=True)
            page.wait_for_timeout(300)
            step("点击替换按钮成功（无异常）", True)
        except Exception as e:
            step("点击替换按钮成功（无异常）", False, str(e)[:80])

        # === 检查 2：单击 text 节点不应进编辑 ===
        text_node = page.locator('.pea-node[data-kind="text"]').first
        text_node.click(force=True)
        page.wait_for_timeout(200)
        is_editing_1 = text_node.locator(".pea-node-text-edit.is-editing").count() > 0
        ce_1 = text_node.locator(".pea-node-text-edit").evaluate("el => el.getAttribute('contenteditable')")
        step(
            "单击 text 节点 → 不进编辑",
            (not is_editing_1) and ce_1 in ("false", None),
            f"is_editing={is_editing_1} contenteditable={ce_1}",
        )

        # === 检查 3：双击 text 节点进编辑 ===
        text_node.dblclick(force=True, position={"x": 50, "y": 30})
        page.wait_for_timeout(300)
        is_editing_2 = text_node.locator(".pea-node-text-edit.is-editing").count() > 0
        ce_2 = text_node.locator(".pea-node-text-edit").evaluate("el => el.getAttribute('contenteditable')")
        step(
            "双击 text 节点 → 进入编辑态",
            is_editing_2 and ce_2 == "true",
            f"is_editing={is_editing_2} contenteditable={ce_2}",
        )

        # === 检查 4：双击 image/video 节点不进编辑（editing 概念不适用，但断言不会破）===
        img_node.dblclick(force=True)
        page.wait_for_timeout(200)
        img_editing = img_node.locator(".pea-node-text-edit.is-editing").count() > 0
        step("双击 image 节点 → 不进文本编辑", not img_editing, f"img_text_editing={img_editing}")

        # 验证 image 节点没有 contenteditable=true 元素（图片无 text-edit）
        ce_in_img = img_node.evaluate(
            "el => Array.from(el.querySelectorAll('[contenteditable=true]')).length"
        )
        step("image 节点内无 contenteditable=true 元素", ce_in_img == 0, f"count={ce_in_img}")

        # === 失焦 → 退出编辑态 ===
        # 单击画布空白处
        page.mouse.click(20, 200)
        page.wait_for_timeout(300)
        is_editing_3 = text_node.locator(".pea-node-text-edit.is-editing").count() > 0
        step("点击空白处后 text 节点退出编辑态", not is_editing_3, f"is_editing={is_editing_3}")

        browser.close()

    print()
    print(f"console errors: {len(console_errors)}")
    for e in console_errors[:5]:
        print(f"  - {e[:160]}")
    if errors:
        print(f"结论: 失败 {len(errors)} 项 ❌")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)
    print("结论: 全部通过 ✅")


if __name__ == "__main__":
    main()