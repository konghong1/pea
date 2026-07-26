"""
verify_e15_three_fixes.py — 验证用户报告的三处严重功能性缺陷已修复

修复 #1 (退格删除节点): 在节点输入框中打字后用退格键，应只编辑文本，不得删除节点。
  验证: 发送前/后 .react-flow__node 数量不变，且输入框文本长度 -1。

修复 #2 (节点图片/视频与电商套图共用接口): 节点图片生成必须打到 /generation/node，
  不得打到电商套图的 /generation/jobs。
  验证: 拦截网络请求，提交图片节点后只见 /generation/node，不见 /generation/jobs(来自节点)。

修复 #3 (节点上多余的「平台配置」按钮): 节点 UI 不得出现 .node-input-pc-chip，
  但用户真正要的比例/分辨率芯片 (.node-input-aspect-chip) 必须保留。
  验证: .node-input-pc-chip 数量为 0；.node-input-aspect-chip 数量 > 0。

硬标准: 0 console error。
"""
import os, json, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
API  = "http://localhost:4100"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = f"e15_{STAMP}@pea.ai"
PW = "Password123"
errors = []
log = []
results = {}

def shot(page, name):
    p = os.path.join(SHOTS, f"e15_{name}.png")
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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

    # 网络拦截：记录所有 /generation/ 相关请求与响应
    gen_requests = []     # 出向 URL 列表
    gen_responses = []    # (url, status)
    page.on("request", lambda r: gen_requests.append(r.url) if "/generation/" in r.url else None)
    page.on("response", lambda r: gen_responses.append((r.url, r.status))
            if "/generation/" in r.url else None)

    # 1) 注册 + 登录
    st, _ = apipost("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    log.append(f"[auth] register -> {st}")
    tok = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})["token"]
    log.append(f"[auth] login OK token_len={len(tok)}")
    st, body = apipost("POST", "/plans/purchase", token=tok, body={"planId": "free"})
    log.append(f"[plans] purchase free -> {st}")

    # 2) 注入登录态并打开
    page.add_init_script(f"localStorage.setItem('pea_token', '{tok}');")
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(1000)
    shot(page, "01_loaded")

    # 3) 工作空间 -> 新建项目 -> 画布
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

    # 4) 双击空白 -> 节点库 -> 选「图片」
    pane = page.locator(".react-flow__pane").first
    pane.dblclick(position={"x": 400, "y": 300})
    page.wait_for_timeout(700)
    try:
        page.locator(".pea-add-menu-item").filter(has_text="图片").first.click(timeout=5000)
        page.wait_for_timeout(1200)
    except Exception as e:
        log.append(f"[node][WARN] 选图片失败: {e}")
    shot(page, "05_image_node")

    assert page.locator(".node-chat-prompt").count() > 0, "NodeChatPrompt 未出现（图片节点未选中）"
    log.append("[check] NodeChatPrompt 出现")

    # ── 修复 #3: 不应有 .node-input-pc-chip；应有 .node-input-aspect-chip（比例/分辨率）──
    pc_count = page.locator(".node-input-pc-chip").count()
    aspect_count = page.locator(".node-input-aspect-chip").count()
    results["fix3_pc_chip_absent"] = (pc_count == 0)
    results["fix3_aspect_chip_present"] = (aspect_count > 0)
    log.append(f"[fix3] pc-chip count={pc_count} (期望0); aspect-chip count={aspect_count} (期望>0)")
    shot(page, "06_image_node_selected")

    # ── 修复 #1: 退格只编辑文本, 不删节点 ──
    inp = page.locator(".node-chat-prompt-input").first
    node_count_before = page.locator(".react-flow__node").count()
    inp.fill("测试文本abc")
    page.wait_for_timeout(200)
    text_before = inp.input_value()
    # 聚焦在输入框内按退格
    inp.focus()
    page.keyboard.press("Backspace")
    page.wait_for_timeout(400)
    text_after = inp.input_value()
    node_count_after = page.locator(".react-flow__node").count()
    results["fix1_node_not_deleted"] = (node_count_after == node_count_before)
    results["fix1_text_edited"] = (len(text_after) == len(text_before) - 1)
    log.append(f"[fix1] 节点数 before={node_count_before} after={node_count_after} "
               f"(期望相等); 文本 '{text_before}' -> '{text_after}' (期望少1字符)")
    shot(page, "07_after_backspace")

    # 5) 选模型 + 发送（触发节点图片生成）
    try:
        page.locator(".node-input-model").click()
        page.wait_for_timeout(900)
        sel = page.locator(".node-model-picker select").first
        opts = sel.locator("option").all_inner_texts()
        log.append(f"[model] 选项: {opts}")
        assert len(opts) > 0, "模型列表为空"
    except Exception as e:
        log.append(f"[model][WARN] 模型选择失败: {e}")

    tapies = page.locator(".node-input-tapies").inner_text()
    log.append(f"[tapies] {tapies}")

    # 重新填回提示词（退格后文本变短，重新填一个完整提示词）
    inp.fill("一只在星空下奔跑的橘猫，霓虹城市，电影感")
    page.wait_for_timeout(200)

    # ── 修复 #2: 提交后请求必须打到 /generation/node, 不得打到 /generation/jobs(节点侧) ──
    gen_requests.clear()
    gen_responses.clear()
    page.locator(".node-chat-prompt-send").click()
    log.append("[action] 已发送图片生成任务")
    page.wait_for_timeout(3000)
    shot(page, "08_submitted")

    node_hits = [u for u in gen_requests if u.rstrip("/").endswith("/generation/node")]
    jobs_hits = [u for u in gen_requests if u.rstrip("/").endswith("/generation/jobs")]
    results["fix2_uses_node_endpoint"] = (len(node_hits) > 0)
    results["fix2_not_using_jobs_endpoint"] = (len(jobs_hits) == 0)
    log.append(f"[fix2] /generation/node 命中={len(node_hits)}; /generation/jobs 命中={len(jobs_hits)} (期望前者>0, 后者=0)")
    for u, s in gen_responses:
        if "/generation/node" in u:
            log.append(f"[fix2] 响应 {u} -> {s}")

    # 汇总
    print("\n".join(log))
    print("\n=== CONSOLE ERRORS ===")
    if errors:
        for e in errors[:40]:
            print("  ", e)
    else:
        print("  (none)")

    fix1 = results["fix1_node_not_deleted"] and results["fix1_text_edited"]
    fix2 = results["fix2_uses_node_endpoint"] and results["fix2_not_using_jobs_endpoint"]
    fix3 = results["fix3_pc_chip_absent"] and results["fix3_aspect_chip_present"]
    overall = fix1 and fix2 and fix3 and (len(errors) == 0)
    print(f"\n[RESULT] fix1(退格不删节点)={fix1} fix2(节点用/generation/node)={fix2} "
          f"fix3(无平台配置按钮但保留比例/分辨率)={fix3}")
    print(f"console_errors={len(errors)}")
    print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
    browser.close()
    raise SystemExit(0 if overall else 1)
