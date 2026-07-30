"""
诊断：NodePromptInput 编辑框点击后光标位置。

复现步骤：
  1. 注入 1 个 image 节点 + 设置其 meta.editorText
  2. 选中该节点，触发 NodeChatPrompt 渲染
  3. 等待编辑框挂载
  4. 往编辑框写入测试文本
  5. 点击文本中段，记录光标位置
  6. 比较期望位置 vs 实际位置
"""
import json
import os
import random
import string
import time
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)


def rand_email():
    return "caret_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))


def apireq(method, path, body=None, token=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, method=method, data=data,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer %s" % token} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.on("console", lambda m: print(f"  [console.{m.type}] {m.text[:300]}"))
        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

        page.add_init_script("localStorage.setItem('__peaDevHooks','1');")

        try:
            # 注册 + 拿 token
            email = rand_email()
            password = "Password123"
            apireq("POST", "/auth/register", {"email": email, "password": password})
            tok = json.loads(urllib.request.urlopen(urllib.request.Request(
                BASE + "/auth/login", method="POST",
                data=json.dumps({"email": email, "password": password}).encode(),
                headers={"Content-Type": "application/json"},
            ), timeout=15).read().decode())["token"]
            cv = json.loads(urllib.request.urlopen(urllib.request.Request(
                BASE + "/canvases", method="POST",
                data=json.dumps({"title": "caret diag", "type": "personal"}).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer %s" % tok},
            ), timeout=15).read().decode())
            canvas_id = cv.get("id")
            canvas_ver = cv.get("version", 1)
            print(f"  [info] user={email} canvas={canvas_id}")

            page.add_init_script("""
                localStorage.setItem('pea_token', '""" + tok + """');
                localStorage.setItem('pea_user', JSON.stringify({ id: 1, email: '""" + email + """' }));
                localStorage.setItem('pea_ui_route', JSON.stringify({ active: 'canvas', canvasId: """ + str(canvas_id) + """ }));
            """)

            import re as _re
            page.route(_re.compile(r".*?/users/me.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": 1, "email": email, "displayName": "Tester",
                                 "balance": 0, "isAdmin": False, "planLevel": 0,
                                 "effectivePlanLevel": 0, "planExpiresAt": None})))
            page.route(_re.compile(r".*?/auth/refresh.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"token": tok})))
            page.route(_re.compile(r".*?/canvases(\?.*)?$"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "data": []})))
            page.route(_re.compile(r".*?/canvases/\d+.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": canvas_id, "title": "caret diag", "version": canvas_ver,
                                 "graph_json": {"nodes": [], "edges": []}})))

            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
            page.wait_for_timeout(1500)

            # 注入 1 个 image 节点 + 预填 prompt（多行中文，足够长能点击中段）
            long_text = "把外套穿到模特身上保持模特的一致性测试文本ABCDEFGHIJKLMN"
            injected = page.evaluate("""([cid, ver, text]) => {
                const cs = window.__canvas.getState();
                cs.setCanvasMeta(cid, ver, 'caret diag');
                cs.loadGraph([
                  { id: 'n1', type: 'pea', position: { x: 300, y: 250 }, data: {
                    kind: 'image', label: '测试', prompt: text, meta: { editorText: text }
                  } }
                ], [], ver);
                window.__ui.getState().setActive('canvas');
                const s2 = window.__canvas.getState();
                return s2.nodes.length;
            }""", [canvas_id, canvas_ver, long_text])
            print(f"  [info] 注入节点数: {injected}")
            page.wait_for_timeout(1500)

            # 选中节点（让 NodeChatPrompt 挂载）
            page.evaluate("() => { window.__canvas.getState().select('n1'); }")
            page.wait_for_timeout(1500)

            # 等编辑框挂载
            page.wait_for_selector('.node-prompt-editor', timeout=10000)
            page.wait_for_timeout(800)

            # 取编辑框位置 + 文本内容
            rect = page.evaluate("""() => {
                const el = document.querySelector('.node-prompt-editor');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { l: r.left, t: r.top, w: r.width, h: r.height,
                         text: el.innerText, html: el.innerHTML,
                         childCount: el.childNodes.length };
            }""")
            if not rect:
                print("  [FAIL] 找不到 .node-prompt-editor")
                return
            print(f"  [info] 编辑框 rect: l={rect['l']:.0f} t={rect['t']:.0f} w={rect['w']:.0f} h={rect['h']:.0f}")
            print(f"  [info] 编辑框文本: '{rect['text']}'")
            print(f"  [info] 编辑框子节点数: {rect['childCount']}")

            # 第 1 次点击：在文本中段（约 50% 位置，水平居中）
            mid_x = rect['l'] + rect['w'] * 0.5
            mid_y = rect['t'] + rect['h'] * 0.5
            page.mouse.click(mid_x, mid_y)
            page.wait_for_timeout(500)

            caret1 = page.evaluate("""() => {
                const el = document.querySelector('.node-prompt-editor');
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return { error: 'no selection' };
                const r = sel.getRangeAt(0);
                return {
                    startOffset: r.startOffset,
                    endOffset: r.endOffset,
                    collapsed: r.collapsed,
                    startContainerNodeType: r.startContainer.nodeType,
                    startContainerText: (r.startContainer.textContent || '').slice(0, 60),
                    fullText: el.innerText,
                };
            }""")
            print(f"  [info] 点击中段后光标: {json.dumps(caret1, ensure_ascii=False)}")
            # 期望：startOffset > 0（不在最前面）
            pos1_ok = isinstance(caret1, dict) and caret1.get('startOffset', 0) > 0
            print(f"  [诊断] 中段点击后光标不在位置 0? {pos1_ok}")

            # 第 2 次点击：在文本开头附近
            head_x = rect['l'] + 30
            head_y = rect['t'] + rect['h'] * 0.5
            page.mouse.click(head_x, head_y)
            page.wait_for_timeout(500)
            caret2 = page.evaluate("""() => {
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return { error: 'no selection' };
                const r = sel.getRangeAt(0);
                return { startOffset: r.startOffset, collapsed: r.collapsed,
                         startContainerText: (r.startContainer.textContent || '').slice(0, 30) };
            }""")
            print(f"  [info] 点击头部后光标: {json.dumps(caret2, ensure_ascii=False)}")
            pos2_ok = isinstance(caret2, dict) and caret2.get('startOffset', 0) <= 5
            print(f"  [诊断] 头部点击后光标在位置 0~5? {pos2_ok}")

            # 第 3 次：再点中段，看是否又会跑回 0
            page.mouse.click(mid_x, mid_y)
            page.wait_for_timeout(500)
            caret3 = page.evaluate("""() => {
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return { error: 'no selection' };
                const r = sel.getRangeAt(0);
                return { startOffset: r.startOffset, collapsed: r.collapsed,
                         startContainerText: (r.startContainer.textContent || '').slice(0, 60) };
            }""")
            print(f"  [info] 再次点击中段后光标: {json.dumps(caret3, ensure_ascii=False)}")
            pos3_ok = isinstance(caret3, dict) and caret3.get('startOffset', 0) > 0
            print(f"  [诊断] 再次中段点击后光标不在位置 0? {pos3_ok}")

            page.screenshot(path=os.path.join(SHOTS, "caret_diag.png"))

            # 总结
            if pos1_ok and pos3_ok:
                print("  [结论] 编辑器光标定位正常，未复现用户反馈的「总在第一个位置」bug。")
            else:
                print("  [结论] 复现 bug：点击非头部位置后，光标仍位于位置 0。")

        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
            page.screenshot(path=os.path.join(SHOTS, "caret_diag_error.png"))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
