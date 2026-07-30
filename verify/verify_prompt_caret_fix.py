"""
验证 fix：点击后 caret 必须落到「点击坐标」对应位置，不能是位置 0。

测试矩阵：
  ① 点击 t1 右侧空白（应在 "穿到" 文本 offset 0）
  ② 点击 t2 左侧空白（应在 "穿到" 文本 offset 3，即 "穿到" 之后）
  ③ 点击 "把" 之前（应在 "把" 文本 offset 0，即编辑器最开头）
  ④ 点击 "模特身上" 末（应在 offset 4，即编辑器最末尾）

每条用例都验证：caret 位置 != 0 OR 落在合理的位置
（点击 ③ 的 caret 位置 = 0 是合法的，因为它就是编辑器最开头）
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
    return "caretv_%s@pea.ai" % "".join(random.choices(string.ascii_lowercase, k=6))


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
    results = []
    def ok(name, detail=""):
        results.append(("PASS", name, detail))
        print("  [PASS] %s%s" % (name, (" -- " + detail) if detail else ""))
    def fail(name, detail=""):
        results.append(("FAIL", name, detail))
        print("  [FAIL] %s: %s" % (name, detail))
    def info(msg):
        print("  [info] %s" % msg)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: None)
        page.on("pageerror", lambda e: print("  [pageerror] %s" % e))

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
                data=json.dumps({"title": "caret fix", "type": "personal"}).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer %s" % tok},
            ), timeout=15).read().decode())
            canvas_id, canvas_ver = cv.get("id"), cv.get("version", 1)
            info("canvas=%s" % canvas_id)

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
                body=json.dumps({"id": canvas_id, "title": "caret fix", "version": canvas_ver, "graph_json": {"nodes": [], "edges": []}})))

            page.goto(BASE + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            page.wait_for_function("() => window.__canvas && window.__ui", timeout=15000)
            page.wait_for_timeout(1500)

            # 注入节点
            page.evaluate("""([cid, ver]) => {
                const cs = window.__canvas.getState();
                cs.setCanvasMeta(cid, ver, 'caret fix');
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
            page.wait_for_timeout(1500)

            # 读 layout 信息
            info_data = page.evaluate("""() => {
                const r = document.querySelector('.node-prompt-editor').getBoundingClientRect();
                const tokens = Array.from(document.querySelectorAll('.node-prompt-editor .pea-ref')).map(t => {
                    const tr = t.getBoundingClientRect();
                    return { id: t.getAttribute('data-node-id'), l: tr.left, r: tr.right, w: tr.width };
                });
                return { l: r.left, t: r.top, w: r.width, h: r.height, tokens };
            }""")
            t1, t2 = info_data['tokens'][0], info_data['tokens'][1]
            click_y = info_data['t'] + info_data['h'] * 0.5
            info("tokens: t1=(%d,%d) t2=(%d,%d)" % (t1['l'], t1['r'], t2['l'], t2['r']))

            def get_caret():
                return page.evaluate("""() => {
                    const sel = window.getSelection();
                    if (!sel || sel.rangeCount === 0) return null;
                    const r = sel.getRangeAt(0);
                    return { offset: r.startOffset, text: (r.startContainer.textContent || '').slice(0, 30) };
                }""")

            # 用例 ①：点击 t1 右侧 → caret 应该在 "穿到" offset 0
            click_x1 = t1['r'] + 8  # t1 右侧 8px（仍在 "穿到" 之前）
            page.mouse.click(click_x1, click_y)
            page.wait_for_timeout(300)
            c1 = get_caret()
            info("用例① click=(%d,%d) → caret=%s" % (click_x1, click_y, c1))
            if c1 and c1['text'] == '穿到' and c1['offset'] == 0:
                ok("用例①：t1 右侧点击 → caret 落在 「穿到」offset 0", json.dumps(c1, ensure_ascii=False))
            else:
                fail("用例①：t1 右侧点击", "caret=%s, 期望 text='穿到' offset=0" % c1)

            # 用例 ②：点击 t2 左侧 → caret 应该在 "穿到" 末尾（offset 2，因为 "穿到" 是 2 字符）
            click_x2 = t2['l'] - 8
            page.mouse.click(click_x2, click_y)
            page.wait_for_timeout(300)
            c2 = get_caret()
            info("用例② click=(%d,%d) → caret=%s" % (click_x2, click_y, c2))
            if c2 and c2['text'] == '穿到' and c2['offset'] == 2:
                ok("用例②：t2 左侧点击 → caret 落在 「穿到」offset 2（= t2 之前）", json.dumps(c2, ensure_ascii=False))
            else:
                fail("用例②：t2 左侧点击", "caret=%s, 期望 text='穿到' offset=2" % c2)

            # 用例 ③：点击编辑器最开头 → caret 应该在 "把" offset 0
            click_x3 = info_data['l'] + 5
            page.mouse.click(click_x3, click_y)
            page.wait_for_timeout(300)
            c3 = get_caret()
            info("用例③ click=(%d,%d) → caret=%s" % (click_x3, click_y, c3))
            if c3 and c3['text'] == '把' and c3['offset'] == 0:
                ok("用例③：编辑器最开头点击 → caret 落在 「把」offset 0", json.dumps(c3, ensure_ascii=False))
            else:
                fail("用例③：编辑器最开头点击", "caret=%s, 期望 text='把' offset=0" % c3)

            # 用例 ④：点击编辑器最末尾 → caret 应该在 "模特身上" offset 4
            click_x4 = info_data['l'] + info_data['w'] - 5
            page.mouse.click(click_x4, click_y)
            page.wait_for_timeout(300)
            c4 = get_caret()
            info("用例④ click=(%d,%d) → caret=%s" % (click_x4, click_y, c4))
            if c4 and c4['text'] == '模特身上' and c4['offset'] == 4:
                ok("用例④：编辑器最末尾点击 → caret 落在 「模特身上」offset 4", json.dumps(c4, ensure_ascii=False))
            else:
                fail("用例④：编辑器最末尾点击", "caret=%s, 期望 text='模特身上' offset=4" % c4)

            # 终极验证：5 次连续点击，caret 都不应该在「把」offset 0
            page.mouse.click(click_x1, click_y)
            page.wait_for_timeout(200)
            page.mouse.click(click_x2, click_y)
            page.wait_for_timeout(200)
            page.mouse.click(click_x4, click_y)
            page.wait_for_timeout(200)
            c5 = get_caret()
            info("用例⑤ 连续三次点击不同位置 → caret=%s" % c5)
            if c5 and c5['text'] == '模特身上' and c5['offset'] == 4:
                ok("用例⑤：连续 3 次不同位置点击，最终 caret 正确", json.dumps(c5, ensure_ascii=False))
            else:
                fail("用例⑤：连续点击后 caret 跳回起点", "caret=%s, 期望 text='模特身上' offset=4" % c5)

            page.screenshot(path=os.path.join(SHOTS, "caret_fix_verify.png"))

        except Exception as e:
            print("  [ERROR] %s" % e)
            import traceback; traceback.print_exc()
            page.screenshot(path=os.path.join(SHOTS, "caret_fix_verify_error.png"))
        finally:
            browser.close()

    pass_count = sum(1 for r in results if r[0] == "PASS")
    fail_count = sum(1 for r in results if r[0] == "FAIL")
    print("\n========== 总结 ==========")
    print("PASS: %d  FAIL: %d  TOTAL: %d" % (pass_count, fail_count, len(results)))
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
