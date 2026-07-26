"""
verify_e17_real_image.py — 验证"调用真实模型出图, 且图真的显示出来"

背景: 之前图片/视频被强制走 Mock (占位 SVG)。用户要求调用真实模型。
本次修复: 编排器直接透传提供商公网 CDN URL (Agnes: platform-outputs.agnes-ai.space),
不再经 MinIO 转存 (该客户端会挂死 + gen/ 前缀未公开读 -> 403 裂图)。

验证项:
  FIX-A (真实模型出图且显示):
    - 点击生成后, 节点结果图 <img> 真实加载 (naturalWidth>0)。
    - 结果图 src 是 https 公网 CDN (以 platform-outputs.agnes-ai.space 开头),
      而非 data:image/svg+xml 占位 (确认走的是真实模型, 不是 mock)。
    - 记录真实耗时 (真实 Agnes 单张 ~30s 属正常, 不作为失败判据)。
  FIX-B (文本节点仍正常): 文本生成回流进内容区。

硬标准: 0 非 chat 路径 console error。
"""
import os, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
API  = "http://localhost:4100"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"e17_{STAMP}@pea.ai"
PW = "Password123"
errors = []
log = []
results = {}

def shot(page, name):
    p = os.path.join(SHOTS, f"e17_{name}.png")
    page.screenshot(path=p)
    log.append(f"[shot] {name} -> {p}")

def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

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
    tok = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})["token"]
    log.append(f"[auth] login OK token_len={len(tok)}")
    st, _ = apipost("POST", "/plans/purchase", token=tok, body={"planId": "free"})
    log.append(f"[plans] purchase free -> {st}")

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

    # ── FIX-A: 建图片节点, 调用真实模型 ──
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

    inp = page.locator(".node-chat-prompt-input").first
    inp.fill("一只在星空下奔跑的橘猫，霓虹城市，电影感")
    page.wait_for_timeout(200)
    t0 = time.time()
    page.locator(".node-chat-prompt-send").click()
    log.append("[action] 真实图片生成已发送 (调用 Agnes 模型)")

    # 等待结果图出现并真正加载 (真实模型 ~30s)
    appeared = False
    loaded = False
    elapsed = None
    src = ""
    deadline = t0 + 240
    while time.time() < deadline:
        if page.locator("img.pea-node-result-preview").count() > 0:
            if elapsed is None:
                elapsed = time.time() - t0
                appeared = True
            # 检查浏览器是否真的把图加载出来 (naturalWidth>0)
            try:
                nw = page.locator("img.pea-node-result-preview").first.evaluate(
                    "el => el.naturalWidth")
            except Exception:
                nw = 0
            src = page.locator("img.pea-node-result-preview").first.get_attribute("src") or ""
            if nw and nw > 0:
                loaded = True
                break
        page.wait_for_timeout(300)
    results["fixA_image_appeared"] = appeared
    results["fixA_image_loaded"] = loaded
    results["fixA_image_elapsed_s"] = round(elapsed, 2) if elapsed is not None else None
    results["fixA_image_src"] = src[:120]
    is_real_cdn = src.startswith("https://platform-outputs.agnes-ai.space")
    is_mock = src.startswith("data:image/svg")
    results["fixA_used_real_model"] = is_real_cdn
    results["fixA_used_mock"] = is_mock
    log.append(f"[fixA] 出现={appeared} 真实加载={loaded} 耗时={results['fixA_image_elapsed_s']}s")
    log.append(f"[fixA] src={src[:90]}... 真实CDN={is_real_cdn} mock={is_mock}")
    shot(page, "08_image_result")

    # ── FIX-B: 文本节点仍正常 ──
    pane.dblclick(position={"x": 900, "y": 300})
    page.wait_for_timeout(700)
    try:
        page.locator(".pea-add-menu-item").filter(has_text="文本").first.click(timeout=5000)
        page.wait_for_timeout(1200)
    except Exception as e:
        log.append(f"[node][WARN] 选文本失败: {e}")
    shot(page, "10_text_node")

    chat_body_count = page.locator(".pea-node-chat-body").count()
    text_edit_count = page.locator(".pea-node-text-edit").count()
    results["fixB_chat_body_removed"] = (chat_body_count == 0)
    results["fixB_content_area_present"] = (text_edit_count > 0)

    tinp = page.locator(".node-chat-prompt-input").first
    tinp.fill("用一句话描述秋天的森林")
    page.wait_for_timeout(200)
    page.locator(".node-chat-prompt-send").click()
    log.append("[action] 文本生成已发送")
    text_appeared = False
    tdead = time.time() + 90
    while time.time() < tdead:
        txt = ""
        try:
            txt = page.locator(".pea-node-text-edit").first.inner_text()
        except Exception:
            txt = ""
        if txt and txt.strip():
            text_appeared = True
            break
        page.wait_for_timeout(500)
    results["fixB_text_in_content_area"] = text_appeared
    log.append(f"[fixB] 内容区出现生成文本={text_appeared}")
    shot(page, "12_text_result")

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
        print(f"  [chat/stream 路径, 尽力验证不计分] 共 {len(chat_errs)} 条")

    fixA = results["fixA_image_appeared"] and results["fixA_image_loaded"] and results["fixA_used_real_model"]
    fixB = results["fixB_chat_body_removed"] and results["fixB_content_area_present"] and results["fixB_text_in_content_area"]
    no_console_err = (len(other_errs) == 0)
    overall = fixA and fixB and no_console_err
    print(f"\n[RESULT] fixA(真实模型出图且显示)={fixA} "
          f"fixB(文本进内容区)={fixB} 非chat_console_errors={len(other_errs)}")
    print(f"[TIMING] 真实图片生成耗时={results['fixA_image_elapsed_s']}s "
          f"(真实 Agnes 模型, 非 mock)")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    browser.close()
    raise SystemExit(0 if overall else 1)
