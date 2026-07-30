"""
诊断：NodePromptInput 编辑框点击后光标位置（带 image token）。

复现步骤：
  1. 注入 2 个 image 节点
  2. 选中第 3 个 image 节点（带 image 引用），预填 prompt 为：把[IMG1]穿到[IMG2]上
  3. 触发 NodeChatPrompt 渲染
  4. 点击文本中段（在"穿到"和"[IMG2]"之间），看光标位置
"""
import json
import os
import random
import string
import urllib.request
import urllib.error
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(SHOTS, exist_ok=True)


def rand_email():
    return "caret2_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))


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

        page.on("console", lambda m: print(f"  [console.{m.type}] {m.text[:200]}") if m.type == "error" else None)
        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

        page.add_init_script("localStorage.setItem('__peaDevHooks','1');")

        try:
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
                data=json.dumps({"title": "caret diag2", "type": "personal"}).encode(),
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
                body=json.dumps({"id": canvas_id, "title": "caret diag2", "version": canvas_ver,
                                 "graph_json": {"nodes": [], "edges": []}})))

            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
            page.wait_for_timeout(1500)

            # 注入：3 个 image 节点（上游 + 选中），用连线连接 + 预填 prompt 包含 2 个 @ token
            injected = page.evaluate("""([cid, ver]) => {
                const cs = window.__canvas.getState();
                cs.setCanvasMeta(cid, ver, 'caret diag2');
                // prompt 含 2 个 image ref token (按 NodePromptInput 协议)
                const prompt = '把<span class="pea-ref" contenteditable="false" data-node-id="i1" data-kind="image" data-pea-ref="1" data-file-key="k1"><span class="pea-ref-inner" contenteditable="false"><img class="pea-ref-thumb" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==" alt=""></span></span>穿到<span class="pea-ref" contenteditable="false" data-node-id="i2" data-kind="image" data-pea-ref="1" data-file-key="k2"><span class="pea-ref-inner" contenteditable="false"><img class="pea-ref-thumb" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==" alt=""></span></span>模特身上';
                cs.loadGraph([
                  { id: 'i1', type: 'pea', position: { x: 100, y: 100 }, data: {
                    kind: 'image', label: '衣服', fileKey: 'k1', resultUrl: 'https://example.com/i1.png'
                  } },
                  { id: 'i2', type: 'pea', position: { x: 100, y: 400 }, data: {
                    kind: 'image', label: '模特', fileKey: 'k2', resultUrl: 'https://example.com/i2.png'
                  } },
                  { id: 'i3', type: 'pea', position: { x: 500, y: 250 }, data: {
                    kind: 'image', label: '生成', prompt: prompt, meta: { editorText: prompt }
                  } }
                ], [
                  { id: 'e1', source: 'i1', target: 'i3' },
                  { id: 'e2', source: 'i2', target: 'i3' }
                ], ver);
                window.__ui.getState().setActive('canvas');
                const s2 = window.__canvas.getState();
                return s2.nodes.length;
            }""", [canvas_id, canvas_ver])
            print(f"  [info] 注入节点数: {injected}")
            page.wait_for_timeout(1500)

            # 选中 i3（触发 NodeChatPrompt）
            page.evaluate("() => { window.__canvas.getState().select('i3'); }")
            page.wait_for_timeout(2000)

            # 等编辑框挂载
            page.wait_for_selector('.node-prompt-editor', timeout=10000)
            page.wait_for_timeout(800)

            # 取编辑框结构 + 内容
            info = page.evaluate("""() => {
                const el = document.querySelector('.node-prompt-editor');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                // 列出所有子节点（text / element）
                const children = Array.from(el.childNodes).map((c, i) => ({
                    idx: i,
                    type: c.nodeType,
                    name: c.nodeName,
                    text: (c.textContent || '').slice(0, 30),
                    rect: c.nodeType === 1 ? c.getBoundingClientRect() : null,
                }));
                return { l: r.left, t: r.top, w: r.width, h: r.height,
                         text: el.innerText, html: el.innerHTML,
                         childCount: el.childNodes.length, children };
            }""")
            if not info:
                print("  [FAIL] 找不到 .node-prompt-editor")
                return
            print(f"  [info] 编辑框 rect: l={info['l']:.0f} t={info['t']:.0f} w={info['w']:.0f} h={info['h']:.0f}")
            print(f"  [info] 编辑框文本: '{info['text']}'")
            print(f"  [info] 子节点数: {info['childCount']}")
            for ch in info['children']:
                print(f"    [{ch['idx']}] type={ch['type']} name={ch['name']} text='{ch['text']}'")

            # 取每个 token 的屏幕位置
            token_rects = page.evaluate("""() => {
                const out = [];
                for (const t of document.querySelectorAll('.node-prompt-editor .pea-ref')) {
                    const r = t.getBoundingClientRect();
                    out.append; // ignore
                    out.push({ id: t.getAttribute('data-node-id'),
                               l: r.left, t: r.top, r: r.right, b: r.bottom,
                               w: r.width, h: r.height });
                }
                return out;
            }""".replace("out.append;", ""))
            print(f"  [info] token rects: {json.dumps(token_rects, ensure_ascii=False)}")

            # 点击 "穿到" 中间（应该在两个 token 之间）
            # 先计算位置
            if len(token_rects) >= 2:
                t1, t2 = token_rects[0], token_rects[1]
                # 在 t1 右边 + 30px 处的位置
                click_x = t1['r'] + 20
                click_y = info['t'] + info['h'] * 0.5
                print(f"  [info] 准备点击 t1 右侧: ({click_x:.0f}, {click_y:.0f})")
                page.mouse.click(click_x, click_y)
                page.wait_for_timeout(500)
                caret = page.evaluate("""() => {
                    const sel = window.getSelection();
                    if (!sel || sel.rangeCount === 0) return { error: 'no selection' };
                    const r = sel.getRangeAt(0);
                    return { startOffset: r.startOffset, collapsed: r.collapsed,
                             startContainerType: r.startContainer.nodeType,
                             startContainerName: r.startContainer.nodeName,
                             startContainerText: (r.startContainer.textContent || '').slice(0, 30) };
                }""")
                print(f"  [info] 点击 t1 右侧后光标: {json.dumps(caret, ensure_ascii=False)}")

                # 在 t2 左侧点击
                click_x2 = t2['l'] - 20
                page.mouse.click(click_x2, click_y)
                page.wait_for_timeout(500)
                caret2 = page.evaluate("""() => {
                    const sel = window.getSelection();
                    if (!sel || sel.rangeCount === 0) return { error: 'no selection' };
                    const r = sel.getRangeAt(0);
                    return { startOffset: r.startOffset, collapsed: r.collapsed,
                             startContainerType: r.startContainer.nodeType,
                             startContainerName: r.startContainer.nodeName,
                             startContainerText: (r.startContainer.textContent || '').slice(0, 30) };
                }""")
                print(f"  [info] 点击 t2 左侧后光标: {json.dumps(caret2, ensure_ascii=False)}")

                # 在编辑器最开头点击（"把" 之前）
                click_x3 = info['l'] + 5
                page.mouse.click(click_x3, click_y)
                page.wait_for_timeout(500)
                caret3 = page.evaluate("""() => {
                    const sel = window.getSelection();
                    if (!sel || sel.rangeCount === 0) return { error: 'no selection' };
                    const r = sel.getRangeAt(0);
                    return { startOffset: r.startOffset, collapsed: r.collapsed,
                             startContainerType: r.startContainer.nodeType,
                             startContainerName: r.startContainer.nodeName,
                             startContainerText: (r.startContainer.textContent || '').slice(0, 30) };
                }""")
                print(f"  [info] 点击编辑器最开头后光标: {json.dumps(caret3, ensure_ascii=False)}")

            # 截图
            page.screenshot(path=os.path.join(SHOTS, "caret_diag2.png"))

        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
            page.screenshot(path=os.path.join(SHOTS, "caret_diag2_error.png"))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
