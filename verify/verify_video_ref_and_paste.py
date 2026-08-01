"""
验证视频节点 @ 图片引用 + 跨节点复制粘贴提示词的两个问题修复。

场景：
1. 上游图片节点 nImgSrc 连接到视频节点 nVideo；在 nVideo 编辑框中 @ 引用 nImgSrc，
   token 应显示为真实图片缩略图（而非 pending 占位图标/文件名）。  -> 问题 A
2. 复制 nVideo 编辑框内容（含 @ token），粘贴到另一个同样连接了 nImgSrc 的视频节点 nVideo2，
   @ 引用应恢复为真实 token 并显示缩略图。                              -> 问题 B（富文本 HTML 路径）
3. 复制纯文本 fallback（@image#nImgSrc:filename）到 nVideo2，应被识别并转换为 token。 -> 问题 B（纯文本路径）
4. 应用内复制时应主动以「富文本 HTML + 纯文本 fallback」双格式写入剪贴板，
   纯文本须含 @image#nImgSrc:filename，保证跨节点/跨应用粘贴可还原。       -> 问题 B（复制格式根因）

说明：为避免 headless 浏览器系统剪贴板权限（NotAllowedError）与浏览器默认序列化不确定性，
paste/copy 均通过 synthetic 事件 + 捕获阶段改写 clipboardData 的方式确定性触发，
直接验证应用层 handlePaste/handleCopy 的真实逻辑。
"""
import os
import sys
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
HERE = Path(__file__).parent
SHOTS = HERE / "shots" / "video_ref_paste"
SHOTS.mkdir(parents=True, exist_ok=True)


def make_test_image() -> str:
    candidates = [
        HERE / "dbg_picker.png",
        HERE / "dbg_editor2.png",
        HERE / "dbg_editor3.png",
        Path("C:/workspace/pea/pea-design/screenshots/_tn_1.png"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    raise FileNotFoundError("找不到测试图片")


def main():
    errors = []

    def step(label, ok, detail=""):
        mark = "✅" if ok else "❌"
        print(f"{mark} {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            errors.append(label)

    test_img = make_test_image()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: print("[pageerror]", e))
        page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

        # 1) 注册并登录
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        if page.locator("text=没有账号？去注册").count() > 0:
            page.locator("text=没有账号？去注册").first.click()
            page.wait_for_timeout(400)
        email = f"vref_{uuid.uuid4().hex[:8]}@pea.ai"
        page.fill('input[placeholder="you@pea.ai"]', email)
        page.fill('input[placeholder="至少 8 位"]', "test1234")
        page.fill('input[placeholder="可选"]', "VRefBot")
        page.locator("form button[type=submit]").click()
        page.wait_for_timeout(2000)
        page.wait_for_selector("text=新建项目", timeout=15000)

        # 2) 创建画布
        cid = page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/canvases', {
                method: 'POST',
                headers: {'Content-Type': 'application/json',
                          ...(token ? {Authorization: `Bearer ${token}`} : {})},
                body: JSON.stringify({title: 'video_ref_paste_test', scope: 'personal'})
            });
            return (await r.json()).id;
        }""")
        print("canvas id:", cid)
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)

        # 3) 注入节点：图片源 + 两个视频节点
        state = page.evaluate("""async (cid) => {
            const store = window.__canvas;
            await store.getState().openCanvas(cid);
            const mk = (id, kind, x, y, extra={}) =>
                ({id, type:'pea', position:{x,y}, data:{kind,label:kind,...extra}});
            store.setState({
              nodes: [
                mk('nImgSrc','image',120,120,{html:'',prompt:'',meta:{}}),
                mk('nVideo','video',520,120,{html:'',prompt:'',meta:{}}),
                mk('nVideo2','video',520,360,{html:'',prompt:'',meta:{}})
              ],
              edges: [], version: 1, dirty: true,
            });
            store.getState().onConnect({source:'nImgSrc', target:'nVideo'});
            store.getState().onConnect({source:'nImgSrc', target:'nVideo2'});
            store.getState().select('nVideo');
            window.__ui.getState().setActive('canvas');
            return { selectedId: store.getState().selectedId,
                     nodes: store.getState().nodes.length,
                     edges: store.getState().edges.length };
        }""", cid)
        print("注入节点:", state)
        page.wait_for_timeout(800)

        # 4) 上传测试图片到 nImgSrc
        src_input = page.locator('.react-flow__node[data-id="nImgSrc"] input[type=file]')
        step("上游图片节点文件输入存在", src_input.count() > 0, f"count={src_input.count()}")
        if src_input.count() > 0:
            src_input.set_input_files(test_img, timeout=15000)
            fk = ""
            for _ in range(20):
                fk = page.evaluate(
                    "() => { const n = window.__canvas.getState().nodes.find(x=>x.id==='nImgSrc'); "
                    "return (n && n.data && n.data.fileKey) || ''; }")
                if fk:
                    break
                page.wait_for_timeout(500)
            step("上传后 nImgSrc 获得 fileKey", bool(fk), f"fileKey={fk[:40]}...")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(SHOTS / "01_after_upload.png"))
        else:
            step("上传后 nImgSrc 获得 fileKey", False, "文件输入不存在")

        def focus_editor(node_id: str):
            # 直接通过 store 切换选中节点，避免上一个节点的输入栏 portal 遮挡目标节点
            page.evaluate(f"""() => {{
                const store = window.__canvas;
                store.getState().clearSelection();
                store.getState().select('{node_id}');
            }}""")
            page.wait_for_timeout(500)
            ed = page.locator(f'.react-flow__node[data-id="{node_id}"] .node-prompt-editor').first
            ed.click()
            page.wait_for_timeout(200)
            return ed

        # 5) 在 nVideo 中 @ 引用图片
        ed = focus_editor("nVideo")
        page.keyboard.type("@")
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "02_video_at_picker.png"))
        step("视频节点 @ picker 已弹出", page.locator(".pea-ref-picker").count() > 0)

        item_count = page.locator(".pea-ref-picker-item").count()
        step("picker 出现图片项", item_count > 0, f"item_count={item_count}")

        thumb_ok = False
        for _ in range(25):
            if page.locator(".pea-ref-picker-thumb").count() > 0:
                thumb_ok = True
                break
            page.wait_for_timeout(400)
        step("picker 缩略图为真实图片", thumb_ok)

        if item_count > 0:
            page.locator(".pea-ref-picker-item").first.click()
            page.wait_for_timeout(600)
        page.screenshot(path=str(SHOTS / "03_video_after_ref.png"))

        # 验证 token 是真实图片（非 pending 占位）— 问题 A
        token_imgs = page.locator('.react-flow__node[data-id="nVideo"] .node-prompt-editor .pea-ref-thumb')
        step("问题A: 视频节点已插入图片 token", token_imgs.count() > 0, f"count={token_imgs.count()}")
        if token_imgs.count() > 0:
            tok_html = token_imgs.first.evaluate("el => el.outerHTML")
            print(f"  [diag] token outerHTML = {tok_html[:260]}")
            token_src = token_imgs.first.get_attribute("src") or ""
            is_renderable = token_src.startswith("http") or token_src.startswith("blob:") or token_src.startswith("/media/")
            step("问题A: token 缩略图可渲染(http/blob/media)", is_renderable,
                 f"src={token_src[:80]}..." if token_src else "src=空")
            is_pending = token_imgs.first.get_attribute("data-pea-pending") == "1"
            step("问题A: token 不是 pending 占位", not is_pending)
        else:
            step("问题A: token 缩略图可渲染(http/blob/media)", False, "无 token")
            step("问题A: token 不是 pending 占位", False, "无 token")

        # 6) 捕获 nVideo 编辑器的真实 HTML + 验证复制处理器双格式输出（问题 B 复制根因）
        captured = page.evaluate("""() => {
            const node = document.querySelector('.react-flow__node[data-id="nVideo"]');
            const ed = node && node.querySelector('.node-prompt-editor');
            if (!ed) return { error: 'no-editor' };
            // 选中全部内容后派发 copy，捕获 React onCopy 写入的剪贴板数据
            const range = document.createRange();
            range.selectNodeContents(ed);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            const recorded = { html: null, plain: null };
            const cap = (e) => {
                Object.defineProperty(e, 'clipboardData', {
                    configurable: true,
                    value: {
                        getData: () => '',
                        setData: (type, val) => { recorded[type] = val; },
                    },
                });
            };
            ed.addEventListener('copy', cap, true);
            ed.dispatchEvent(new ClipboardEvent('copy', { bubbles: true, cancelable: true }));
            ed.removeEventListener('copy', cap, true);
            return { html: ed.innerHTML, recordedHtml: recorded['text/html'], recordedPlain: recorded['text/plain'] };
        }""")
        print("  [diag] copy capture:", {k: (v[:120] if isinstance(v, str) else v) for k, v in (captured or {}).items()})
        step("复制处理器写入 text/html（含 data-pea-ref）",
             bool(captured.get("recordedHtml")) and "data-pea-ref" in (captured.get("recordedHtml") or ""),
             f"len={len(captured.get('recordedHtml') or '')}")
        step("复制处理器写入 text/plain fallback（含 @image#nImgSrc）",
             bool(captured.get("recordedPlain")) and "@image#nImgSrc" in (captured.get("recordedPlain") or ""),
             f"plain={(captured.get('recordedPlain') or '')[:80]}")
        nVideo_html = captured.get("html") or ""

        # 7) 富文本粘贴：把 nVideo 的 HTML 粘贴到 nVideo2（问题 B 主路径）
        ed2 = focus_editor("nVideo2")
        page.evaluate("""(html) => {
            const node = document.querySelector('.react-flow__node[data-id="nVideo2"]');
            const ed = node && node.querySelector('.node-prompt-editor');
            if (!ed) return;
            ed.focus();
            const range = document.createRange();
            range.selectNodeContents(ed);
            range.collapse(false);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            const cap = (e) => {
                Object.defineProperty(e, 'clipboardData', {
                    configurable: true,
                    value: {
                        getData: (t) => (t === 'text/html' ? (html || '') : ''),
                        setData: () => {},
                    },
                });
            };
            ed.addEventListener('paste', cap, true);
            ed.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true }));
            ed.removeEventListener('paste', cap, true);
        }""", nVideo_html)
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "04_video2_after_paste.png"))

        pasted_tokens = page.locator('.react-flow__node[data-id="nVideo2"] .node-prompt-editor .pea-ref')
        step("问题B: 粘贴后 nVideo2 存在 @ token", pasted_tokens.count() > 0, f"count={pasted_tokens.count()}")
        if pasted_tokens.count() > 0:
            pasted_imgs = page.locator('.react-flow__node[data-id="nVideo2"] .node-prompt-editor .pea-ref-thumb')
            step("问题B: 粘贴后 token 包含缩略图", pasted_imgs.count() > 0, f"count={pasted_imgs.count()}")
            if pasted_imgs.count() > 0:
                pasted_src = pasted_imgs.first.get_attribute("src") or ""
                is_renderable = pasted_src.startswith("http") or pasted_src.startswith("blob:") or pasted_src.startswith("/media/")
                step("问题B: 粘贴后缩略图可渲染", is_renderable,
                     f"src={pasted_src[:80]}..." if pasted_src else "src=空")
            # 诊断：打印粘贴后编辑器 innerHTML
            diag = page.locator('.react-flow__node[data-id="nVideo2"] .node-prompt-editor').first.evaluate("el => el.innerHTML")
            print(f"  [diag] nVideo2 innerHTML after paste = {diag[:300]}")
        else:
            diag = page.locator('.react-flow__node[data-id="nVideo2"] .node-prompt-editor').first.evaluate("el => el.innerHTML")
            print(f"  [diag] nVideo2 innerHTML after paste = {diag[:300]}")
            step("问题B: 粘贴后 token 包含缩略图", False, "无 token")

        # 8) 纯文本 fallback 粘贴：清空 nVideo2 后粘贴 @image#nImgSrc:filename（问题 B 文本路径）
        ed2 = focus_editor("nVideo2")
        page.keyboard.press("Control+a")
        page.wait_for_timeout(200)
        page.keyboard.press("Delete")
        page.wait_for_timeout(200)

        file_name = page.evaluate(
            "() => { const n = window.__canvas.getState().nodes.find(x=>x.id==='nImgSrc'); "
            "return (n && n.data && n.data.meta && n.data.meta.fileName) || 'Clipboard_Screenshot.png'; }"
        )
        fallback_text = f"让模特参考 @image#nImgSrc:{file_name} 的姿态"
        page.evaluate("""(text) => {
            const node = document.querySelector('.react-flow__node[data-id="nVideo2"]');
            const ed = node && node.querySelector('.node-prompt-editor');
            if (!ed) return;
            ed.focus();
            const range = document.createRange();
            range.selectNodeContents(ed);
            range.collapse(false);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            const cap = (e) => {
                Object.defineProperty(e, 'clipboardData', {
                    configurable: true,
                    value: {
                        getData: (t) => (t === 'text/html' ? '' : (text || '')),
                        setData: () => {},
                    },
                });
            };
            ed.addEventListener('paste', cap, true);
            ed.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true }));
            ed.removeEventListener('paste', cap, true);
        }""", fallback_text)
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "05_video2_fallback_paste.png"))

        fallback_tokens = page.locator('.react-flow__node[data-id="nVideo2"] .node-prompt-editor .pea-ref')
        step("问题B: fallback 文本粘贴后存在 @ token", fallback_tokens.count() > 0,
             f"count={fallback_tokens.count()}")
        if fallback_tokens.count() > 0:
            fallback_imgs = page.locator('.react-flow__node[data-id="nVideo2"] .node-prompt-editor .pea-ref-thumb')
            step("问题B: fallback token 包含缩略图", fallback_imgs.count() > 0, f"count={fallback_imgs.count()}")
            if fallback_imgs.count() > 0:
                fb_src = fallback_imgs.first.get_attribute("src") or ""
                is_renderable = fb_src.startswith("http") or fb_src.startswith("blob:") or fb_src.startswith("/media/")
                step("问题B: fallback 缩略图可渲染", is_renderable,
                     f"src={fb_src[:80]}..." if fb_src else "src=空")
        else:
            diag = page.locator('.react-flow__node[data-id="nVideo2"] .node-prompt-editor').first.evaluate("el => el.innerHTML")
            print(f"  [diag] nVideo2 innerHTML after fallback = {diag[:300]}")
            step("问题B: fallback token 包含缩略图", False, "无 token")

        browser.close()

    if errors:
        print(f"\n❌ 失败项: {errors}")
        return 1
    print("\n🎉 全部验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
