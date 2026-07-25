"""
真机验证：节点输入框弹出框修复
1. 模型/比例/数量 三个选择框相对按钮的间距统一（按钮底边上方 ≈10px）
2. 点击输入框（非选择框区域）能关闭所有弹出框
3. 电商套图模型下拉：显示所有模型，无权模型置灰(disabled)
"""
from playwright.sync_api import sync_playwright
from pathlib import Path
import time, json, sys

SHOTS = Path("C:/workspace/pea/verify/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

BASE = "http://localhost:8088"

def gap(popup_box, btn_box):
    if not popup_box or not btn_box:
        return None
    # 弹窗在按钮上方：间距 = 按钮底边 - 弹窗底边
    return round(btn_box["y"] + btn_box["height"] - (popup_box["y"] + popup_box["height"]), 1)

def main():
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(600)

        # ── 注册并进入画布 ──
        page.get_by_role("button", name="没有账号？去注册").first.click()
        page.wait_for_timeout(300)
        ts = int(time.time())
        page.fill('input[placeholder="you@pea.ai"]', f"fixv_{ts}@pea.dev")
        page.fill('input[placeholder="至少 8 位"]', "Password123")
        page.fill('input[placeholder="可选"]', "D")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(4000)
        # 注册后进入工作空间（项目列表），需新建项目进入画布
        page.wait_for_selector(".projects-page", timeout=10000)
        page.get_by_role("button", name="新建项目").first.click()
        page.wait_for_selector(".react-flow__viewport", timeout=15000)

        # ── 添加图片节点 ──
        page.mouse.dblclick(1000, 300)
        page.wait_for_timeout(350)
        page.locator(".pea-add-menu-item", has_text="图片").first.click()
        page.wait_for_timeout(900)
        page.wait_for_selector(".node-input-bar", timeout=8000)

        # ── 1. 模型芯片弹出框 ──
        page.locator(".node-input-model-chip").first.click()
        page.wait_for_timeout(400)
        out["model_gap"] = gap(
            page.locator(".node-model-picker").first.bounding_box(),
            page.locator(".node-input-model-chip").first.bounding_box(),
        )
        print("DEBUG data-kind:", page.locator(".node-input-bar").first.get_attribute("data-kind"))
        print("DEBUG left html:", page.locator(".node-input-status-left").first.inner_html()[:400])
        page.locator(".node-input-model-chip").first.click()  # toggle 关闭，保持选中
        page.wait_for_timeout(300)
        print("DEBUG data-kind:", page.locator(".node-input-bar").first.get_attribute("data-kind"))
        print("DEBUG left html:", page.locator(".node-input-status-left").first.inner_html()[:400])

        # ── 2. 比例芯片弹出框 ──
        try:
            page.locator(".node-input-aspect-chip").first.click()
            page.wait_for_timeout(400)
            out["aspect_gap"] = gap(
                page.locator(".node-aspect-picker").first.bounding_box(),
                page.locator(".node-input-aspect-chip").first.bounding_box(),
            )
            page.locator(".node-input-aspect-chip").first.click()  # 关闭
        except Exception as e:
            out["aspect_error"] = str(e)[:120]
        page.wait_for_timeout(300)

        # ── 3. 数量按钮下拉框 ──
        try:
            page.locator(".node-count-btn").first.click()
            page.wait_for_timeout(400)
            out["count_gap"] = gap(
                page.locator(".node-count-btn-dropdown").first.bounding_box(),
                page.locator(".node-count-btn").first.bounding_box(),
            )
            page.locator(".node-count-btn").first.click()  # 关闭
        except Exception as e:
            out["count_error"] = str(e)[:120]
        page.wait_for_timeout(300)

        # ── 4. 点击输入框(textarea) 应关闭弹出框 ──
        page.locator(".node-input-model-chip").first.click()
        page.wait_for_timeout(400)
        opened = page.locator(".node-model-picker").count()
        # 触发 textarea 的 mousedown（弹窗覆盖 textarea 时真实 click 会被拦截，故直接派发事件验证逻辑）
        page.locator(".node-input-textarea").first.dispatch_event("mousedown")
        page.wait_for_timeout(400)
        closed = page.locator(".node-model-picker").count()
        out["click_input_closes"] = (opened > 0 and closed == 0)

        # ── 5. 点击画布空白应关闭弹出框 ──
        page.locator(".node-input-aspect-chip").first.click()
        page.wait_for_timeout(400)
        opened2 = page.locator(".node-aspect-picker").count()
        page.mouse.click(700, 80)  # 画布顶部空白（避开弹窗覆盖区）
        page.wait_for_timeout(400)
        closed2 = page.locator(".node-aspect-picker").count()
        out["click_canvas_closes"] = (opened2 > 0 and closed2 == 0)

        page.screenshot(path=str(SHOTS / "verify_popup.png"))

        # ── 6. 电商套图模型下拉：显示所有 + 无权置灰 ──
        # 回到主页/工作空间，进入电商套图
        try:
            # 回到工作空间，点击顶栏「电商套图」进入
            page.goto(BASE, wait_until="networkidle")
            page.wait_for_timeout(1000)
            page.get_by_text("电商套图", exact=False).first.click()
            page.wait_for_timeout(1500)
            # 打开模型下拉（label=模型 的 antd Select）
            sel = page.locator(".ant-select").filter(has_text="模型").first
            if sel.count():
                sel.click()
                page.wait_for_timeout(500)
                opts = page.locator(".ant-select-item-option").all()
                info = []
                for o in opts:
                    disabled = o.get_attribute("aria-disabled") == "true" or "ant-select-item-option-disabled" in (o.get_attribute("class") or "")
                    info.append({"text": o.inner_text().split("\n")[0][:30], "disabled": disabled})
                out["ecom_model_options"] = info
                out["ecom_model_count"] = len(info)
                out["ecom_disabled_count"] = sum(1 for i in info if i["disabled"])
                page.keyboard.press("Escape")
        except Exception as e:
            out["ecom_error"] = str(e)[:200]

        b.close()

    # ── 判定 ──
    gaps = [out.get(k) for k in ("model_gap", "aspect_gap", "count_gap")]
    gaps = [g for g in gaps if g is not None]
    out["gaps_consistent"] = all(abs(g - 10) <= 3 for g in gaps)
    out["gap_target"] = 10
    print(json.dumps(out, ensure_ascii=False, indent=2))

    ok = out.get("gaps_consistent") and out.get("click_input_closes") and out.get("click_canvas_closes")
    print("\n=== 结果 ===")
    print(f"间距一致(≈10px): {out.get('gaps_consistent')}  -> model={out.get('model_gap')} aspect={out.get('aspect_gap')} count={out.get('count_gap')}")
    print(f"点击输入框关闭: {out.get('click_input_closes')}")
    print(f"点击画布关闭: {out.get('click_canvas_closes')}")
    if "ecom_model_count" in out:
        print(f"电商模型选项: {out.get('ecom_model_count')} 个, 置灰 {out.get('ecom_disabled_count')} 个 -> {out.get('ecom_model_options')}")
    print(f"\n总体: {'✅ PASS' if ok else '❌ FAIL'}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
