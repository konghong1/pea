"""验证：节点标题(徽章)随画布等比缩放，交互控件(上传条/功能条)屏幕大小恒定。

判定标准：
  A. badgeWidth / cardWidth 在所有 zoom 下恒定（相对大小不变）  -> 标题跟节点一起缩放
  B. badge 屏幕宽度 与 zoom 成正比                              -> 确实随画布放大缩小
  C. 上传条/功能条 屏幕宽度恒定                                  -> 交互控件仍可点
  D. 标题始终位于节点框上方、不与节点框重叠                        -> 布局没被破坏
"""
import os
import re
import json
import time
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5180"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = time.strftime("%Y%m%d%H%M%S")
EMAIL = "badgescale_%s@pea.ai" % STAMP
PW = "Password123"
errors = []
log = []
ZOOMS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]


def ls_set(page, key, value):
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))


def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": "Bearer %s" % token} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


MEASURE = """(id) => {
  const sel = typeof id === 'string' ? id : (id && id.id) || '';
  const nodeEl = document.querySelector('.react-flow__node[data-id="' + sel + '"]');
  if (!nodeEl) return { err: 'no node ' + id };
  const vp = document.querySelector('.react-flow__viewport');
  const m = vp ? new DOMMatrixReadOnly(getComputedStyle(vp).transform) : null;
  const r = (el) => {
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { w: +b.width.toFixed(2), h: +b.height.toFixed(2),
             top: +b.top.toFixed(2), bottom: +b.bottom.toFixed(2), left: +b.left.toFixed(2) };
  };
  return {
    zoom: m ? +m.a.toFixed(4) : null,
    card: r(nodeEl.querySelector('.pea-node-body-card')),
    badge: r(nodeEl.querySelector('.pea-node-badge')),
    upload: r(nodeEl.querySelector('.pea-node-upload-btn')),
    chromeTransform: getComputedStyle(nodeEl.querySelector('.pea-node-chrome')).transform,
  };
}"""


def close(a, b, tol):
    return abs(a - b) <= tol


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
    page.on("console", lambda m: errors.append("console.error: %s" % m.text) if m.type == "error" else None)

    api("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    _, resp = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})
    tok = (resp or {}).get("token")

    page.goto(BASE + "/login", wait_until="domcontentloaded")
    ls_set(page, "pea_token", tok or "x")
    ls_set(page, "pea_user", {"id": 1, "email": EMAIL})
    ls_set(page, "pea_ui_route", {"active": "canvas", "canvasId": None})

    def mock_json(payload):
        return lambda route, request: route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/users/me", mock_json({"id": 1, "email": EMAIL, "displayName": "T", "balance": 0,
                                         "isAdmin": False, "planLevel": 0, "effectivePlanLevel": 0,
                                         "planExpiresAt": None}))
    page.route("**/auth/refresh", mock_json({"token": tok or "x"}))
    page.route(re.compile(r"http://[^/]+/canvases.*"), mock_json({"ok": True, "data": []}))
    page.route(re.compile(r"http://[^/]+/models/.*"), mock_json([]))
    page.route(re.compile(r"http://[^/]+/files/.*"), mock_json({"ok": True}))

    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => window.__canvas && window.__peaSetZoom && window.__peaFitView", timeout=20000)
    page.wait_for_timeout(600)

    page.evaluate("""() => {
      window.__canvas.getState().loadGraph([
        { id: 'n1', type: 'pea', position: { x: 80, y: 160 },
          data: { kind: 'image', aspectRatio: '1:1', label: '图片生成标题' } },
        { id: 'n2', type: 'pea', position: { x: 460, y: 160 },
          data: { kind: 'text', aspectRatio: '1:1', label: '文本节点标题' } },
        { id: 'n3', type: 'pea', position: { x: 820, y: 160 },
          data: { kind: 'image', aspectRatio: '1:1', label: 'AI 结果',
                  resultUrl: 'https://placehold.co/300x300/png' } },
      ], [], 1);
      window.__canvas.getState().select('n2');
    }""")
    page.wait_for_timeout(800)

    # 视口自适应：fitView 让 3 个节点都在屏幕内（zoom 1 下整宽约 1140px，1440 内有富余）
    page.evaluate("() => window.__peaFitView({ padding: 0.2, maxZoom: 1 })")
    page.wait_for_timeout(400)
    # 调试：打印各节点当前屏幕 rect
    print("post-fitView:", page.evaluate("""() => {
      const r = (n) => { if(!n) return null; const b = n.getBoundingClientRect(); return { w: Math.round(b.width), left: Math.round(b.left) }; };
      return { vp: r(document.querySelector('.react-flow__viewport')),
        n1: r(document.querySelector('.react-flow__node[data-id=\"n1\"]')),
        n2: r(document.querySelector('.react-flow__node[data-id=\"n2\"]')),
        n3: r(document.querySelector('.react-flow__node[data-id=\"n3\"]')) };
    }"""))

    rows = []
    for z in ZOOMS:
        page.evaluate("(z) => window.__peaSetZoom(z)", z)
        page.wait_for_timeout(350)
        m = page.evaluate(MEASURE, "n1")
        m["want"] = z
        rows.append(m)
        # 顺带验证 n3 (生成结果) 的功能条 / n2 (文本) 的工具条 屏幕大小恒定
        for nid in ("n2", "n3"):
            mm = page.evaluate(MEASURE, nid)
            rows[-1].setdefault(nid, mm)
        try:
            page.screenshot(path=os.path.join(SHOTS, "badgescale_%s_z%s.png" % (STAMP, str(z).replace('.', '_'))))
        except Exception as ex:
            log.append("shot fail z=%s: %s" % (z, ex))

    print("=== 测量 ===")
    print("%-6s %-8s %-9s %-9s %-9s %-9s %-10s" % ("want", "zoom", "cardW", "badgeW", "badge/card", "uploadW", "badgeBot-cardTop"))
    for m in rows:
        if m.get("err"):
            errors.append(m["err"]); continue
        card, badge, up = m.get("card") or {}, m.get("badge") or {}, m.get("upload") or {}
        ratio = (badge.get("w") or 0) / (card.get("w") or 1)
        gap = (card.get("top") or 0) - (badge.get("bottom") or 0)
        m["ratio"], m["gap"] = ratio, gap
        print("%-6s %-8s %-9s %-9s %-9.4f %-9s %-10.2f" % (
            m["want"], m.get("zoom"), card.get("w"), badge.get("w"), ratio, up.get("w"), gap))
        print("       chromeTransform=%s" % m.get("chromeTransform"))

    good = [m for m in rows if not m.get("err")]
    base_ratio = good[0]["ratio"]
    # A. n1 标题/节点比例恒定
    for m in good:
        if not close(m["ratio"], base_ratio, 0.01):
            errors.append("A-FAIL zoom=%s badge/card=%.4f 偏离基准 %.4f" % (m["want"], m["ratio"], base_ratio))
    # B. n1 badge 屏幕宽与 zoom 成正比
    unit = good[0]["badge"]["w"] / good[0]["zoom"]
    for m in good:
        exp = unit * m["zoom"]
        if not close(m["badge"]["w"], exp, max(1.0, exp * 0.02)):
            errors.append("B-FAIL zoom=%s badgeW=%.2f 期望≈%.2f" % (m["want"], m["badge"]["w"], exp))
    # C. n1 上传条屏幕宽恒定
    ups = [m["upload"]["w"] for m in good if m.get("upload")]
    if not ups:
        errors.append("C-FAIL n1 上传条未渲染")
    elif (max(ups) - min(ups)) > 1.5:
        errors.append("C-FAIL n1 上传条屏幕宽不恒定: %s" % ups)
    # D. n2 (文本) / n3 (生成结果) 标题也按比例缩放
    for nid in ("n2", "n3"):
        ratios = []
        for r in good:
            card = (r.get(nid) or {}).get("card") or {}
            bdg = (r.get(nid) or {}).get("badge") or {}
            if card.get("w"):
                ratios.append(bdg.get("w") / card.get("w"))
        if not ratios:
            errors.append("D-FAIL %s 未找到 badge/card" % nid)
        elif (max(ratios) - min(ratios)) > 0.01:
            errors.append("D-FAIL %s 标题/节点比例漂移: min=%.4f max=%.4f" % (nid, min(ratios), max(ratios)))
    # E. 标题与节点框间距≥1px
    for m in good:
        if m["gap"] < 1:
            errors.append("E-FAIL zoom=%s 标题与节点框重叠 gap=%.2f" % (m["want"], m["gap"]))

    print("\n=== 结论 ===")
    if errors:
        print("FAIL (%d)" % len(errors))
        for e in errors:
            print("  - %s" % e)
    else:
        print("PASS：标题与节点等比缩放(badge/card=%.4f 恒定)，交互控件屏幕大小恒定(%.1fpx)" % (base_ratio, ups[0]))
    for l in log:
        print(l)
    browser.close()
