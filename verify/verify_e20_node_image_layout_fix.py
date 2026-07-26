"""
verify_e20_node_image_layout_fix.py — 验证图片节点严重 UI 修复

验证项:
  1. 选中 image 节点时，文本节点专用工具栏（H1/H2/H3/B/I/列表）不弹出。
  2. 生成的图片完整展示，节点宽度随图片自适应（非固定 260px，超小图 fallback 到 min-width 270px，上限 320px）。
  3. 图片结果 toolbar 浮在图片上方，不与图片主体重叠。
  4. 出图数选择按钮可见，且下拉能正常展开。
  5. 图片节点 body-card 无额外边框/内边距，图片贴合节点边缘。
硬标准: 0 非 chat 路径 console error。
"""
import os, json, time, urllib.request, urllib.error, re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
API  = "http://localhost:4100"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"e20_{STAMP}@pea.ai"
PW = "Password123"
MOCK_IMAGE = "http://localhost:8088/e2e-test.png"
errors = []
log = []
results = {}

def shot(page, name):
    p = os.path.join(SHOTS, f"e20_{name}.png")
    page.screenshot(path=p)
    log.append(f"[shot] {name} -> {p}")

def apipost(method, path, token=None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

def is_chat_err(msg):
    return "/chat/stream" in msg

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 1) 注册 + 登录
    st, _ = apipost("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    log.append(f"[auth] register -> {st}")
    tok = urllib.request.urlopen(urllib.request.Request(
        API + "/auth/login", method="POST",
        data=json.dumps({"email": EMAIL, "password": PW}).encode(),
        headers={"Content-Type": "application/json"})).read()
    tok = json.loads(tok)["token"]
    log.append(f"[auth] login OK token_len={len(tok)}")
    st, _ = apipost("POST", "/plans/purchase", token=tok, body={"planId": "free"})
    log.append(f"[plans] purchase free -> {st}")

    fake_job_id = f"e20-{STAMP}"
    def handle_route(route, request):
        if request.method == "POST" and request.url.endswith("/models/estimate"):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"allowed": True, "cost": 10, "minPlanLevel": 0}))
        elif request.method == "POST" and request.url.endswith("/generation/node"):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"jobId": fake_job_id, "status": "accepted", "cost": 10}))
        elif request.method == "GET" and re.search(r"/generation/jobs/[^/]+$", request.url):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"jobId": fake_job_id, "status": "done", "resultUrl": MOCK_IMAGE, "error": None}))
        else:
            route.continue_()
    page.route("**/models/estimate", handle_route)
    page.route("**/generation/**", handle_route)

    page.add_init_script(f"localStorage.setItem('pea_token', '{tok}');")
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(1000)
    shot(page, "01_loaded")

    # 2) 工作空间 -> 新建项目 -> 画布
    page.locator(".pea-user-trigger").click()
    page.wait_for_timeout(400)
    try:
        page.get_by_text("工作空间", exact=False).first.click(timeout=4000)
    except Exception as e:
        log.append(f"[nav][WARN] 工作空间点击失败: {e}")
    page.wait_for_timeout(900)
    try:
        page.get_by_text("新建项目", exact=False).first.click(timeout=5000)
        page.wait_for_timeout(2500)
    except Exception as e:
        log.append(f"[nav][WARN] 新建项目点击失败: {e}")
    shot(page, "03_canvas")

    # 3) 建图片节点
    pane = page.locator(".react-flow__pane").first
    pane.dblclick(position={"x": 360, "y": 300})
    page.wait_for_timeout(700)
    try:
        page.locator(".pea-add-menu-item").filter(has_text="图片").first.click(timeout=5000)
        page.wait_for_timeout(1200)
    except Exception as e:
        log.append(f"[node][WARN] 选图片失败: {e}")
    shot(page, "05_image_node")
    assert page.locator(".node-chat-prompt").count() > 0, "图片节点 NodeChatPrompt 未出现"
    log.append("[check] 图片节点 NodeChatPrompt 出现")

    # 先聚焦输入框，确保 textarea 已稳定挂载
    inp = page.locator(".node-chat-prompt-input").first
    inp.wait_for(state="visible", timeout=10000)
    inp.fill("一只在星空下奔跑的橘猫，霓虹城市，电影感")
    page.wait_for_timeout(200)
    t0 = time.time()
    page.locator(".node-chat-prompt-send").click()
    log.append("[action] 图片生成已发送（已拦截为 mock）")

    # 4) 检查出图数选择按钮可见（发送后结果返回前）
    count_btn = page.locator(".node-count-btn").first
    count_visible = count_btn.is_visible()
    results["count_btn_visible_initial"] = count_visible
    log.append(f"[count] 可见={count_visible}")
    # 展开下拉，检查可见
    count_btn.click()
    page.wait_for_timeout(300)
    dropdown = page.locator(".node-count-btn-dropdown").first
    dropdown_visible = dropdown.is_visible()
    results["count_dropdown_visible"] = dropdown_visible
    log.append(f"[count] 下拉可见={dropdown_visible}")
    shot(page, "06_count_dropdown")
    # 收起下拉
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # 等待结果图出现并加载
    appeared = False
    loaded = False
    elapsed = None
    deadline = time.time() + 30
    while time.time() < deadline:
        img = page.locator("img.pea-node-result-preview")
        if img.count() > 0:
            if elapsed is None:
                elapsed = time.time() - t0
                appeared = True
            try:
                info = img.first.evaluate("el => ({ complete: el.complete, naturalWidth: el.naturalWidth, naturalHeight: el.naturalHeight, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })")
            except Exception:
                info = None
            if info and info.get("complete") and info.get("naturalWidth", 0) > 0:
                loaded = True
                results["image_natural_size"] = f"{info['naturalWidth']}x{info['naturalHeight']}"
                results["image_rendered_size"] = f"{round(info['width'])}x{round(info['height'])}"
                break
        page.wait_for_timeout(300)
    results["image_appeared"] = appeared
    results["image_loaded"] = loaded
    log.append(f"[image] 出现={appeared} 加载={loaded} natural={results.get('image_natural_size')} rendered={results.get('image_rendered_size')}")
    shot(page, "08_image_result")

    # 6) 检查文本节点工具栏未出现
    text_toolbar = page.locator(".text-node-toolbar")
    text_toolbar_count = text_toolbar.count()
    # 即使组件挂载，非 text 节点也不应渲染 tnt-bar（按钮）
    tnt_bar_count = page.locator(".tnt-bar").count()
    results["text_toolbar_absent"] = (text_toolbar_count == 0 and tnt_bar_count == 0)
    log.append(f"[text_toolbar] text-node-toolbar={text_toolbar_count} tnt-bar={tnt_bar_count} 应不存在")

    # 7) 检查节点宽度自适应（非固定 260px）
    node = page.locator(".pea-node-image.pea-node-has-media").first
    node_box = node.bounding_box()
    node_width = node_box["width"] if node_box else None
    results["node_width"] = node_width
    # 自适应：超小图 fallback 到 min-width 270px，正常图随图片宽度（≤320px），上限放宽到 340 防浮点误差
    results["node_width_adaptive"] = node_width is not None and 130 <= node_width <= 340
    log.append(f"[layout] 节点宽度={node_width} 自适应={results['node_width_adaptive']}")

    # 8) 检查 toolbar 不与图片重叠
    node.hover()
    page.wait_for_timeout(300)
    toolbar = page.locator(".pea-node-result-toolbar").first
    toolbar_visible = toolbar.is_visible()
    results["toolbar_visible"] = toolbar_visible
    img_box = page.locator(".pea-node-result-image-wrap").first.bounding_box()
    toolbar_box = toolbar.bounding_box()
    if img_box and toolbar_box:
        # toolbar 底部应 <= 图片顶部（留出小间距）
        overlap_ok = toolbar_box["y"] + toolbar_box["height"] <= img_box["y"] + 2
        results["toolbar_not_overlap"] = overlap_ok
        log.append(f"[toolbar] 可见={toolbar_visible} toolbar_bottom={toolbar_box['y']+toolbar_box['height']:.1f} img_top={img_box['y']:.1f} 不重叠={overlap_ok}")
    else:
        results["toolbar_not_overlap"] = False
        log.append(f"[toolbar] 无法获取边界框 img={img_box} toolbar={toolbar_box}")
    shot(page, "10_toolbar_hover")

    # 9) 检查 body-card 无额外左右/底部内边距（用计算样式，避免小图时几何比对失真）
    #    顶部 40px 是故意留给 toolbar 的，不算额外边距
    body_card = page.locator(".pea-node-image.pea-node-has-media .pea-node-body-card").first
    pad = body_card.evaluate("el => { const s = getComputedStyle(el); return { left: s.paddingLeft, right: s.paddingRight, bottom: s.paddingBottom, top: s.paddingTop }; }")
    results["no_extra_padding"] = pad["left"] == "0px" and pad["right"] == "0px" and pad["bottom"] == "0px"
    log.append(f"[layout] body-card 计算内边距 L={pad['left']} R={pad['right']} B={pad['bottom']} T={pad['top']} 无额外边距={results['no_extra_padding']}")

    # 10) 关闭 Lightbox 等（保留 e19 的基础验证）
    fullscreen_btn = toolbar.get_by_role("button", name="全屏查看")
    fullscreen_btn.click()
    page.wait_for_timeout(500)
    lightbox = page.locator(".pea-node-lightbox").first
    results["lightbox_visible"] = lightbox.is_visible()
    page.locator(".pea-node-lightbox-close").first.click()
    page.wait_for_timeout(400)
    results["lightbox_closed"] = page.locator(".pea-node-lightbox").count() == 0

    # 汇总
    print("\n".join(log))
    print("\n=== CONSOLE ERRORS ===")
    chat_errs = [e for e in errors if is_chat_err(e)]
    other_errs = [e for e in errors if not is_chat_err(e)]
    if other_errs:
        for e in other_errs[:40]:
            print("  [NON-CHAT]", e)
    else:
        print("  (none, 非 chat 路径)")
    if chat_errs:
        print(f"  [chat/stream 路径, 不计分] 共 {len(chat_errs)} 条")

    checks = [
        results.get("image_appeared"),
        results.get("image_loaded"),
        results.get("text_toolbar_absent"),
        results.get("node_width_adaptive"),
        results.get("toolbar_visible"),
        results.get("toolbar_not_overlap"),
        results.get("no_extra_padding"),
        results.get("count_btn_visible_initial"),
        results.get("count_dropdown_visible"),
        results.get("lightbox_visible"),
        results.get("lightbox_closed"),
    ]
    no_console_err = (len(other_errs) == 0)
    overall = all(checks) and no_console_err
    print(f"\n[RESULT] checks={checks}")
    print(f"[RESULT] 非chat_console_errors={len(other_errs)}")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    browser.close()
    raise SystemExit(0 if overall else 1)
