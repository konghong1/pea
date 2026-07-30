"""
深度诊断：观察点击时编辑框 DOM 变化 + caret 变化时序。
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
    return "caret3_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))


def apireq(method, path, body=None, token=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, method=method, data=data, headers={
        "Content-Type": "application/json",
        **({"Authorization": "Bearer %s" % token} if token else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"  [console.{m.type}] {m.text[:300]}"))
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
                data=json.dumps({"title": "caret3", "type": "personal"}).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer %s" % tok},
            ), timeout=15).read().decode())
            canvas_id, canvas_ver = cv.get("id"), cv.get("version", 1)
            print(f"  [info] canvas={canvas_id}")

            page.add_init_script("""
                localStorage.setItem('pea_token', '""" + tok + """');
                localStorage.setItem('pea_user', JSON.stringify({ id: 1, email: '""" + email + """' }));
                localStorage.setItem('pea_ui_route', JSON.stringify({ active: 'canvas', canvasId: """ + str(canvas_id) + """ }));
            """)

            import re as _re
            page.route(_re.compile(r".*?/users/me.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": 1, "email": email, "displayName": "Tester", "balance": 0, "isAdmin": False, "planLevel": 0, "effectivePlanLevel": 0, "planExpiresAt": None})))
            page.route(_re.compile(r".*?/auth/refresh.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json", body=json.dumps({"token": tok})))
            page.route(_re.compile(r".*?/canvases(\?.*)?$"), lambda r, req: r.fulfill(
                status=200, content_type="application/json", body=json.dumps({"ok": True, "data": []})))
            page.route(_re.compile(r".*?/canvases/\d+.*"), lambda r, req: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"id": canvas_id, "title": "caret3", "version": canvas_ver, "graph_json": {"nodes": [], "edges": []}})))

            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
            page.wait_for_timeout(1500)

            page.evaluate("""([cid, ver]) => {
                const cs = window.__canvas.getState();
                cs.setCanvasMeta(cid, ver, 'caret3');
                const prompt = '把<span class="pea-ref" contenteditable="false" data-node-id="i1" data-kind="image" data-pea-ref="1" data-file-key="k1"><span class="pea-ref-inner" contenteditable="false"><img class="pea-ref-thumb" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==" alt=""></span></span>穿到<span class="pea-ref" contenteditable="false" data-node-id="i2" data-kind="image" data-pea-ref="1" data-file-key="k2"><span class="pea-ref-inner" contenteditable="false"><img class="pea-ref-thumb" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==" alt=""></span></span>模特身上';
                cs.loadGraph([
                    { id: 'i1', type: 'pea', position: { x: 100, y: 100 }, data: { kind: 'image', label: '衣服', fileKey: 'k1', resultUrl: 'https://example.com/i1.png' } },
                    { id: 'i2', type: 'pea', position: { x: 100, y: 400 }, data: { kind: 'image', label: '模特', fileKey: 'k2', resultUrl: 'https://example.com/i2.png' } },
                    { id: 'i3', type: 'pea', position: { x: 500, y: 250 }, data: { kind: 'image', label: '生成', prompt, meta: { editorText: prompt } } }
                ], [
                    { id: 'e1', source: 'i1', target: 'i3' },
                    { id: 'e2', source: 'i2', target: 'i3' }
                ], ver);
                window.__ui.getState().setActive('canvas');
            }""", [canvas_id, canvas_ver])
            page.wait_for_timeout(1500)
            page.evaluate("() => { window.__canvas.getState().select('i3'); }")
            page.wait_for_selector('.node-prompt-editor', timeout=10000)
            page.wait_for_timeout(1500)  # 等 resolvedThumbs / 占位替换完成

            # 安装 MutationObserver + caret tracker
            page.evaluate("""() => {
                window.__diagLog = [];
                const editor = document.querySelector('.node-prompt-editor');
                if (!editor) return;
                // 1. 监听 DOM 变化
                const mo = new MutationObserver((mutations) => {
                    for (const m of mutations) {
                        window.__diagLog.push({
                            t: performance.now(),
                            type: m.type,
                            target: m.target.nodeName,
                            targetDataNode: m.target.getAttribute && m.target.getAttribute('data-node-id'),
                            added: m.addedNodes.length,
                            removed: m.removedNodes.length,
                            attr: m.attributeName,
                        });
                    }
                });
                mo.observe(editor, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'class', 'data-pea-pending'] });
                // 2. 监听 caret 变化
                const tracker = () => {
                    const sel = window.getSelection();
                    if (sel && sel.rangeCount > 0) {
                        const r = sel.getRangeAt(0);
                        const text = (r.startContainer.textContent || '').slice(0, 30);
                        window.__diagLog.push({
                            t: performance.now(),
                            kind: 'caret',
                            offset: r.startOffset,
                            nodeType: r.startContainer.nodeType,
                            nodeName: r.startContainer.nodeName,
                            text,
                        });
                    } else {
                        window.__diagLog.push({ t: performance.now(), kind: 'caret', none: true });
                    }
                    requestAnimationFrame(tracker);
                };
                requestAnimationFrame(tracker);
            }""")
            page.wait_for_timeout(300)  # 让 tracker 启动

            # 标记点击前
            page.evaluate("() => { window.__diagLog.push({t: performance.now(), kind: 'CLICK_START'}); }")

            # 读 token rect + 编辑框 rect
            rects = page.evaluate("""() => {
                const r = document.querySelector('.node-prompt-editor').getBoundingClientRect();
                const tokens = Array.from(document.querySelectorAll('.node-prompt-editor .pea-ref')).map(t => {
                    const tr = t.getBoundingClientRect();
                    return { id: t.getAttribute('data-node-id'), l: tr.left, r: tr.right };
                });
                return { l: r.left, t: r.top, w: r.width, h: r.height, tokens };
            }""")
            print(f"  [info] editor rect: {rects['l']:.0f},{rects['t']:.0f} {rects['w']:.0f}x{rects['h']:.0f}")
            print(f"  [info] tokens: {json.dumps(rects['tokens'])}")

            # 点击 t1 右侧（应该在 "穿到" 前）
            t1 = rects['tokens'][0]
            click_x = t1['r'] + 8
            click_y = rects['t'] + rects['h'] * 0.5
            print(f"  [info] 点击位置: ({click_x:.0f}, {click_y:.0f})")
            page.mouse.click(click_x, click_y)
            page.wait_for_timeout(500)

            page.evaluate("() => { window.__diagLog.push({t: performance.now(), kind: 'CLICK_END'}); }")
            page.wait_for_timeout(200)

            # 读 log
            log = page.evaluate("() => window.__diagLog || []")
            print(f"  [info] diag log 条数: {len(log)}")
            # 抽出来
            for entry in log:
                print(f"    {json.dumps(entry, ensure_ascii=False)}")

            # 读最终 caret
            final_caret = page.evaluate("""() => {
                const sel = window.getSelection();
                if (!sel || sel.rangeCount === 0) return null;
                const r = sel.getRangeAt(0);
                return { offset: r.startOffset, text: (r.startContainer.textContent || '').slice(0, 30) };
            }""")
            print(f"  [info] 最终 caret: {json.dumps(final_caret, ensure_ascii=False)}")

            page.screenshot(path=os.path.join(SHOTS, "caret_diag3.png"))
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback; traceback.print_exc()
            page.screenshot(path=os.path.join(SHOTS, "caret_diag3_error.png"))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
