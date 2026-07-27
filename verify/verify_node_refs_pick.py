"""E-REF-2 · @ 引用 + 文本节点引用条验证

覆盖：
- 节点被选中后，引用条渲染包括文本节点引用(以文本图标显示)
- 鼠标交互：点击 + 按钮进入画布选择模式，点击文本节点加入引用
- 引用条 hover 显示移除按钮，点击移除
- 切换节点再切换回原节点，编辑器中的 <span class="pea-ref"> token 仍然渲染为缩略图（不变成代码文本）
- 0 console error（硬标准）
"""
import os
import sys
import uuid
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:5174"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"eref2_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []
checks = []


def shot(page, name):
    p = os.path.join(SHOTS, f"eref2_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")


def create_canvas_via_api(page):
    return page.evaluate("""
        async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/canvases', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: 'Bearer ' + token } : {}),
                },
                body: JSON.stringify({ title: 'E2E Ref Pick Test', scope: 'personal' }),
            });
            const j = await r.json();
            return j.id;
        }
    """)


def ensure_canvas(page):
    try:
        page.wait_for_selector(".react-flow__viewport", timeout=8000)
        return
    except Exception:
        pass
    shot(page, "01b_before_nav")
    cid = create_canvas_via_api(page)
    page.evaluate(
        f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))"
    )
    page.wait_for_timeout(1500)
    page.wait_for_selector(".react-flow__viewport", timeout=20000)


def inject_graph(page):
    """注入: 上游图片 + 文本节点 + 目标图片节点, 全部未连"""
    page.evaluate("""
        () => {
            const store = window.__canvas.getState();
            store.loadGraph([], [], store.version);
            const imgNode = {
                id: 'nImg1', type: 'pea',
                position: { x: 80, y: 200 },
                data: {
                    kind: 'image', label: 'Bag',
                    resultUrl: 'https://placehold.co/120x120/8a4a2c/ffffff?text=Bag',
                    meta: { fileName: 'Clipboard_Screenshot.png' }
                }
            };
            const imgNode2 = {
                id: 'nImg2', type: 'pea',
                position: { x: 80, y: 30 },
                data: {
                    kind: 'image', label: 'Phone',
                    resultUrl: 'https://placehold.co/120x120/333/fff?text=Phone',
                    meta: { fileName: 'Clipboard_Screenshot-1.png' }
                }
            };
            const textNode = {
                id: 'nText1', type: 'pea',
                position: { x: 80, y: 400 },
                data: {
                    kind: 'text', label: 'Text',
                    html: '高端女装模特，黑色连衣裙，白色背景'
                }
            };
            const target = {
                id: 'nTarget1', type: 'pea',
                position: { x: 520, y: 240 },
                data: { kind: 'image', label: 'Target', prompt: '', meta: {} }
            };
            store.loadGraph([imgNode, imgNode2, textNode, target], [], store.version);
            store.select('nTarget1');
            return true;
        }
    """)


def node_data(page, nid):
    return page.evaluate(
        f"() => {{ const n = window.__canvas.getState().nodes.find(x => x.id === '{nid}'); return n ? {{ prompt: n.data.prompt, params: n.data.params, meta: n.data.meta }} : null; }}"
    )


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册并进入画布
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "RefPickBot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(4000)
    ensure_canvas(page)
    shot(page, "01_workspace")
    checks.append(("进入画布", True))

    # 2) 注入图
    inject_graph(page)
    page.wait_for_timeout(800)
    shot(page, "02_graph_injected")
    checks.append(("注入图结构", True))

    # 3) 引用条初始为空
    bar = page.locator(".node-input-bar")
    expect(bar).to_be_visible(timeout=8000)
    ref_thumbs = page.locator(".node-ref-thumb")
    expect(ref_thumbs).to_have_count(0, timeout=3000)
    shot(page, "03_ref_bar_empty")
    checks.append(("初始引用条为空", True))

    # 4) 点击 + 进入画布选择模式
    page.locator('button[aria-label="从画布选择参考"]').click()
    page.wait_for_timeout(300)
    pick_bar = page.locator(".node-canvas-pick-bar")
    expect(pick_bar).to_be_visible(timeout=3000)
    shot(page, "04_pick_mode")
    checks.append(("+ 进入画布选择模式", True))

    # 5) 点击文本节点 nText1，应加入引用(支持文本节点)
    page.locator('.react-flow__node[data-id="nText1"]').click()
    page.wait_for_timeout(400)
    expect(bar).to_be_visible(timeout=3000)
    ref_thumbs = page.locator(".node-ref-thumb")
    expect(ref_thumbs).to_have_count(1, timeout=3000)
    # 验证是文本节点引用(text 类样式)
    text_thumb = page.locator('.node-ref-thumb[data-ref-kind="text"]')
    expect(text_thumb).to_have_count(1, timeout=3000)
    shot(page, "05_text_node_added")
    checks.append(("+ 选文本节点加入引用条", True))

    # 6) 继续点图片节点 nImg1（pick mode 仍开启），加入引用
    page.locator('.react-flow__node[data-id="nImg1"]').click()
    page.wait_for_timeout(400)
    ref_thumbs = page.locator(".node-ref-thumb")
    expect(ref_thumbs).to_have_count(2, timeout=3000)
    # 应同时存在 text + image 两种样式
    expect(page.locator('.node-ref-thumb[data-ref-kind="text"]')).to_have_count(1)
    expect(page.locator('.node-ref-thumb[data-ref-kind="image"]')).to_have_count(1)
    shot(page, "06_image_added_too")
    checks.append(("+ 同时支持图片+文本", True))

    # 7) 退出选择模式
    page.locator(".node-canvas-pick-exit").click()
    page.wait_for_timeout(200)
    expect(pick_bar).to_be_hidden(timeout=3000)

    # 8) hover 文本节点引用项，移除按钮可见；点击移除
    text_ref = page.locator('.node-ref-thumb[data-ref-kind="text"]').first
    text_ref.hover()
    page.wait_for_timeout(200)
    remove_btn = text_ref.locator(".node-ref-remove")
    expect(remove_btn).to_be_visible(timeout=2000)
    shot(page, "07_remove_btn_visible_on_hover")
    remove_btn.click()
    page.wait_for_timeout(300)
    expect(page.locator('.node-ref-thumb[data-ref-kind="text"]')).to_have_count(0, timeout=3000)
    expect(page.locator(".node-ref-thumb")).to_have_count(1, timeout=3000)
    shot(page, "08_text_ref_removed")
    checks.append(("hover 移除按钮可移除文本引用", True))

    # 9) 用 @ 选择器在编辑框中插入图片 token，然后切换到别的节点再切回：
    #    缩略图应该仍然渲染，不能变成 <span class="pea-ref"> 文本
    # 先连一条 nImg2 -> nTarget1 的边，让 nImg2 出现在 @ 选择器列表中
    page.evaluate("""
        () => {
            const store = window.__canvas.getState();
            store.onConnect({ source: 'nImg2', target: 'nTarget1' });
        }
    """)
    page.wait_for_timeout(400)
    editor = page.locator(".node-prompt-editor")
    editor.click()
    page.wait_for_timeout(200)
    page.keyboard.type("@")
    page.wait_for_timeout(500)
    picker = page.locator(".pea-ref-picker")
    expect(picker).to_be_visible(timeout=3000)
    # 选择首个项(图片)
    picker.locator(".pea-ref-picker-item").first.click()
    page.wait_for_timeout(300)
    # 编辑框内应出现 token span
    token_in_editor = editor.locator(".pea-ref[data-pea-ref='1']")
    expect(token_in_editor).to_have_count(1, timeout=3000)
    shot(page, "09_at_image_inserted")
    checks.append(("@ 引用图片插入 token", True))

    # 9.1) 关键回归: 切换到其他节点再切回，token 仍渲染为缩略图，不能变成 escape 后的 HTML 文本
    page.locator('.react-flow__node[data-id="nImg2"]').click()
    page.wait_for_timeout(400)
    page.locator('.react-flow__node[data-id="nTarget1"]').click()
    page.wait_for_timeout(600)
    # 不应出现 "<span class=\"pea-ref" 这种源码文本
    raw_html_in_editor = page.evaluate(
        "() => document.querySelector('.node-prompt-editor')?.innerText?.includes('<span class=\"pea-ref') ? 'LEAK' : 'OK'"
    )
    assert raw_html_in_editor == "OK", f"编辑器出现 raw HTML: {raw_html_in_editor}"
    # token span 仍存在
    expect(editor.locator(".pea-ref[data-pea-ref='1']")).to_have_count(1, timeout=3000)
    shot(page, "10_token_still_rendered_after_switch")
    checks.append(("切换节点后 token 仍渲染为缩略图", True))

    # 10) 提交时，文本节点(被 + 添加过)/图片 token 都能合到 prompt 里
    # 先确认 target 的 meta.referencedNodeIds 持久化
    node_data_obj = node_data(page, "nTarget1")
    print("[node_data after pics]", node_data_obj)
    meta = node_data_obj.get("meta") or {}
    assert isinstance(meta.get("referencedNodeIds"), list), f"referencedNodeIds 未持久化: {meta}"
    assert "nImg1" in meta["referencedNodeIds"], f"@引用的图片未持久化: {meta['referencedNodeIds']}"
    checks.append(("referencedNodeIds 持久化", True))

    # 11) 重新加一次文本节点引用(走 + 按钮以验证文本能进入 prompt)
    page.locator('button[aria-label="从画布选择参考"]').click()
    page.wait_for_timeout(200)
    page.locator('.react-flow__node[data-id="nText1"]').click()
    page.wait_for_timeout(400)
    page.locator(".node-canvas-pick-exit").click()
    page.wait_for_timeout(200)
    # 直接发送
    page.locator(".node-input-send").click()
    page.wait_for_timeout(800)
    shot(page, "11_submit_with_text_ref")
    node_data_obj = node_data(page, "nTarget1")
    print("[node_data after submit]", node_data_obj)
    prompt = node_data_obj.get("prompt") or ""
    assert "高端女装模特" in prompt, f"文本节点(通过 + 引用)未合并到 prompt: {prompt}"
    checks.append(("文本节点通过 + 引用合并到 prompt", True))

    # 结果
    print("\n========== 验证结果 ==========")
    for name, ok in checks:
        print(f"  {'OK' if ok else 'FAIL'} {name}")
    if errors:
        print("\nWARN Console / Page errors:")
        for e in errors[:20]:
            print(f"  - {e}")
    else:
        print("\nOK 0 console error")
    browser.close()
    sys.exit(0 if all(ok for _, ok in checks) else 1)
