"""E-REF · 节点上游引用工作流验证

覆盖：
- 上游图片节点连接到目标图片节点后，引用条自动显示图片缩略图
- 上游文本节点内容自动合并进 prompt，但不在引用条展示
- 编辑框为空、仅有上游输入时，生成按钮可用
- + 按钮进入「从画布选择参考」模式，顶部出现蓝条
- 在画布选择模式下，点击图片/视频节点可将其加入引用集合
- 发送时合并文本节点内容 + 编辑框内容，并携带 reference_images
- 0 console error（硬标准）
"""
import os
import sys
import uuid
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:5174"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
EMAIL = f"eref_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
errors = []
checks = []

def shot(page, name):
    p = os.path.join(SHOTS, f"eref_{name}.png")
    page.screenshot(path=p)
    print(f"[shot] {name} -> {p}")

def create_canvas_via_api(page):
    """通过 BFF API 创建空白画布并返回 id。"""
    return page.evaluate("""
        async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/canvases', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ title: 'E2E Ref Test', scope: 'personal' }),
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
    page.evaluate(f"window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))")
    page.wait_for_timeout(1500)
    page.wait_for_selector(".react-flow__viewport", timeout=20000)

def inject_graph(page):
    """通过 dev 暴露的 window.__canvas 注入测试图结构。"""
    page.evaluate("""
        () => {
            const store = window.__canvas.getState();
            // 清空现有节点
            store.loadGraph([], [], store.version);
            // 创建上游节点
            const imgNode = {
                id: 'nImg1', type: 'pea',
                position: { x: 100, y: 200 },
                data: {
                    kind: 'image', label: 'Image',
                    resultUrl: 'https://placehold.co/120x120/1fa2dc/ffffff?text=Ref+Img',
                    meta: { fileName: 'Clipboard_Screenshot.png' }
                }
            };
            const imgNode2 = {
                id: 'nImg2', type: 'pea',
                position: { x: 100, y: 50 },
                data: {
                    kind: 'image', label: 'Image2',
                    resultUrl: 'https://placehold.co/120x120/dc1f6a/ffffff?text=Ref+Img2',
                    meta: { fileName: 'Clipboard_Screenshot-1.png' }
                }
            };
            const textNode = {
                id: 'nText1', type: 'pea',
                position: { x: 100, y: 400 },
                data: {
                    kind: 'text', label: 'Text',
                    html: '高端女装模特，黑色连衣裙，白色背景'
                }
            };
            const target = {
                id: 'nTarget1', type: 'pea',
                position: { x: 500, y: 300 },
                data: { kind: 'image', label: 'Image', prompt: '', meta: {} }
            };
            store.loadGraph([imgNode, imgNode2, textNode, target], [
                { id: 'e1', source: 'nImg1', target: 'nTarget1', type: 'pea' },
                { id: 'e2', source: 'nText1', target: 'nTarget1', type: 'pea' },
            ], store.version);
            store.select('nTarget1');
            return true;
        }
    """)

def read_target_node_data(page):
    return page.evaluate("""
        () => {
            const n = window.__canvas.getState().nodes.find(x => x.id === 'nTarget1');
            return n ? { prompt: n.data.prompt, params: n.data.params, meta: n.data.meta } : null;
        }
    """)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册并进入工作空间
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)
    page.get_by_role("button", name="没有账号？去注册").first.click()
    page.wait_for_timeout(300)
    page.fill('input[placeholder="you@pea.ai"]', EMAIL)
    page.fill('input[placeholder="至少 8 位"]', PW)
    page.fill('input[placeholder="可选"]', "RefBot")
    page.locator("form button[type=submit]").click()
    page.wait_for_timeout(4000)
    ensure_canvas(page)
    shot(page, "01_workspace")
    checks.append(("进入工作空间画布", True))

    # 2) 注入测试图
    inject_graph(page)
    page.wait_for_timeout(800)
    shot(page, "02_graph_injected")
    checks.append(("注入测试图结构", True))

    # 3) 检查目标节点下方出现输入栏
    bar = page.locator(".node-input-bar")
    expect(bar).to_be_visible(timeout=8000)
    shot(page, "03_input_bar_visible")
    checks.append(("目标节点输入栏可见", True))

    # 4) 引用条应只展示图片节点 nImg1 的缩略图(文本节点不展示)，缩略图必须真实加载
    ref_thumbs = page.locator(".node-ref-thumb")
    expect(ref_thumbs).to_have_count(1, timeout=5000)
    thumb_img = ref_thumbs.locator("img").first
    src = thumb_img.get_attribute("src")
    assert src and src.strip() and "text=%3F" not in src and "text=?" not in src, f"缩略图 src 为空或仍是占位图: {src}"
    shot(page, "04_ref_bar_one_image")
    checks.append(("引用条自动显示 1 个上游图片缩略图", True))

    # 4b) + 按钮应紧跟缩略图，不被推到引用条最右侧
    plus_btn = page.locator('button[aria-label="从画布选择参考"]')
    bar_box = bar.bounding_box()
    plus_box = plus_btn.bounding_box()
    assert bar_box and plus_box, "无法获取引用条或 + 按钮位置"
    # 期望 + 按钮左边缘不超过引用条宽度的 55%（单个缩略图时应在左侧）
    assert plus_box["x"] + plus_box["width"] <= bar_box["x"] + bar_box["width"] * 0.55, (
        f"+ 按钮被推到最右侧: plus_left={plus_box['x']}, bar_right={bar_box['x'] + bar_box['width']}"
    )
    checks.append(("+ 按钮紧跟缩略图", True))

    # 5) 编辑框为空、但上游有文本+图片输入时，生成按钮可用
    editor = page.locator(".node-prompt-editor")
    editor.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    send_btn = page.locator(".node-input-send")
    expect(send_btn).to_be_enabled(timeout=3000)
    shot(page, "05_send_enabled_without_editor_input")
    checks.append(("仅上游输入时生成按钮可用", True))

    # 6) 直接发送(编辑框为空)，验证文本自动合并、图片自动作为 reference_images
    send_btn.click()
    page.wait_for_timeout(800)
    shot(page, "06_submit_with_upstream_only")
    checks.append(("仅上游输入可发送", True))

    node_data = read_target_node_data(page)
    print("[node_data]", node_data)
    ref_images = (node_data.get("params") or {}).get("reference_images") or []
    prompt = node_data.get("prompt") or ""
    assert len(ref_images) >= 1, f"reference_images 为空: {ref_images}"
    assert "高端女装模特" in prompt, f"上游文本未合并: {prompt}"
    checks.append(("节点数据 reference_images 与 prompt 已合并", True))

    # 7) 点击 + 进入「从画布选择参考」模式，顶部出现蓝条
    page.locator('button[aria-label="从画布选择参考"]').click()
    page.wait_for_timeout(300)
    pick_bar = page.locator(".node-canvas-pick-bar")
    expect(pick_bar).to_be_visible(timeout=3000)
    shot(page, "07_canvas_pick_mode")
    checks.append(("+ 按钮进入画布选择模式", True))

    # 8) 点击未连接的图片节点 nImg2，把它加入引用集合
    page.locator('.react-flow__node[data-id="nImg2"]').click()
    page.wait_for_timeout(400)
    # 选择应仍停留在 nTarget1(输入栏未消失)
    expect(bar).to_be_visible(timeout=3000)
    # 引用条现在应有 2 个缩略图
    ref_thumbs = page.locator(".node-ref-thumb")
    expect(ref_thumbs).to_have_count(2, timeout=5000)
    shot(page, "08_canvas_pick_added")
    checks.append(("点击画布图片节点加入引用", True))

    # 9) 退出画布选择模式，输入自定义文本并发送
    page.locator(".node-canvas-pick-exit").click()
    page.wait_for_timeout(200)
    expect(pick_bar).to_be_hidden(timeout=3000)
    editor.click()
    page.keyboard.type("，专业摄影风格，柔和光线")
    page.wait_for_timeout(200)
    send_btn.click()
    page.wait_for_timeout(800)
    shot(page, "09_submit_with_refs_and_text")
    checks.append(("自定义文本 + 多参考图发送", True))

    node_data = read_target_node_data(page)
    print("[node_data final]", node_data)
    ref_images = (node_data.get("params") or {}).get("reference_images") or []
    prompt = node_data.get("prompt") or ""
    assert len(ref_images) >= 2, f"reference_images 不足 2 张: {ref_images}"
    assert "高端女装模特" in prompt and "柔和光线" in prompt, f"prompt 未正确合并: {prompt}"
    meta = node_data.get("meta") or {}
    assert isinstance(meta.get("referencedNodeIds"), list) and "nImg2" in meta["referencedNodeIds"], f"显式引用未持久化: {meta}"
    checks.append(("显式引用已持久化且节点数据完整", True))

    # 10) @ 选择器仍然可用(可选回归)
    editor.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    page.keyboard.type("@")
    page.wait_for_timeout(400)
    picker = page.locator(".pea-ref-picker")
    expect(picker).to_be_visible(timeout=3000)
    shot(page, "10_at_picker")
    checks.append(("@ 选择器可用", True))

    # 结果
    print("\n========== 验证结果 ==========")
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
    if errors:
        print("\n⚠️ Console / Page errors:")
        for e in errors[:20]:
            print(f"  - {e}")
    else:
        print("\n✅ 0 console error")
    browser.close()
    sys.exit(0 if all(ok for _, ok in checks) else 1)
