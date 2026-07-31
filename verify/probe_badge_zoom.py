"""Probe: 节点标题(徽章)在不同画布 zoom 下的实际屏幕尺寸 vs 节点框尺寸。

目的：判定标题当前是「屏幕恒定大小(counter-scale)」还是「随画布等比缩放」。
输出每个 zoom 下：
  - node body-card 屏幕宽度
  - badge 屏幕宽度/高度/字号
  - badge宽 / node宽 的比值（等比缩放时该比值恒定）
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
EMAIL = "badgezoom_%s@pea.ai" % STAMP
PW = "Password123"
log = []


def ls_set(page, key, value):
    page.evaluate("localStorage.setItem(%s, JSON.stringify(%s));" % (json.dumps(key), json.dumps(value)))


def api(method, path, token=None, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer %s" % token} if token else {}),
        },
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
  const nodeEl = document.querySelector('.react-flow__node[data-id="' + id + '"]');
  if (!nodeEl) return { err: 'no node' };
  const card = nodeEl.querySelector('.pea-node-body-card');
  const chrome = nodeEl.querySelector('.pea-node-chrome');
  const badge = nodeEl.querySelector('.pea-node-badge');
  const vp = document.querySelector('.react-flow__viewport');
  const m = vp ? new DOMMatrixReadOnly(getComputedStyle(vp).transform) : null;
  const r = (el) => {
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { w: +b.width.toFixed(2), h: +b.height.toFixed(2), top: +b.top.toFixed(2), left: +b.left.toFixed(2) };
  };
  const cs = badge ? getComputedStyle(badge) : null;
  return {
    zoom: m ? +m.a.toFixed(4) : null,
    invVar: getComputedStyle(document.documentElement).getPropertyValue('--pea-inv-zoom').trim(),
    chromeDataZoom: chrome ? chrome.getAttribute('data-zoom') : null,
    chromeTransform: chrome ? getComputedStyle(chrome).transform : null,
    card: r(card),
    badge: r(badge),
    badgeFontPx: cs ? cs.fontSize : null,
    node: r(nodeEl),
  };
}"""


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("pageerror", lambda e: log.append("pageerror: %s" % e))

    api("POST", "/auth/register", body={"email": EMAIL, "password": PW})
    st, resp = api("POST", "/auth/login", body={"email": EMAIL, "password": PW})
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
    page.wait_for_function("() => window.__canvas", timeout=20000)
    page.wait_for_timeout(600)

    page.evaluate("""() => {
      window.__canvas.getState().loadGraph([
        { id: 'n1', type: 'pea', position: { x: 200, y: 200 },
          data: { kind: 'image', aspectRatio: '1:1', label: '图片生成标题' } },
      ], [], 1);
    }""")
    page.wait_for_timeout(500)

    results = []
    for z in [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]:
        page.evaluate("(z) => window.__peaSetZoom(z)", z)
        page.wait_for_timeout(350)
        m = page.evaluate(MEASURE, "n1")
        m["want"] = z
        results.append(m)
        page.screenshot(path=os.path.join(SHOTS, "badgezoom_%s_z%s.png" % (STAMP, str(z).replace('.', '_'))))

    print("=== 测量结果 ===")
    for m in results:
        if m.get("err"):
            print(m)
            continue
        card = m.get("card") or {}
        badge = m.get("badge") or {}
        ratio = (badge.get("w") or 0) / (card.get("w") or 1)
        print("want=%-4s realZoom=%-7s invVar=%-8s chromeZoom=%-6s | cardW=%-7s badgeW=%-7s badgeH=%-6s font=%-6s | badge/card=%.4f"
              % (m["want"], m.get("zoom"), m.get("invVar"), m.get("chromeDataZoom"),
                 card.get("w"), badge.get("w"), badge.get("h"), m.get("badgeFontPx"), ratio))
        print("     chromeTransform=%s" % m.get("chromeTransform"))
    print("\n--- log ---")
    for l in log:
        print(l)
    browser.close()
