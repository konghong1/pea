"""验证节点媒体交互 4 个修复点

1. 图片节点刷新后编辑框有内容时发送按钮可用
2. 视频节点输入内容后刷新不丢失
3. 视频节点作为上游被引用时显示视频缩略图，hover 可播放
4. 删除连线后上游视频缩略图从引用条移除

测试 1/2 的「刷新」场景：先真实输入内容 → 等待画布自动保存(auto-save) →
page.reload() → 重新从服务端 openCanvas 打开同一画布 → 选中节点，断言编辑框恢复内容且发送按钮可用。
（in-memory 的 loadGraph 状态在 reload 后消失，必须用服务端持久化往返才能真正复现刷新场景。）
"""
import os, sys, uuid, time
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5174"
EMAIL = f"vmf_{uuid.uuid4().hex[:8]}@pea.dev"
PW = "Password123"
VIDEO_URL = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"


def main():
    errors = []
    def step(label, ok, detail=""):
        icon = "PASS" if ok else "FAIL"
        print(f"[{icon}] {label}  {detail}")
        if not ok: errors.append(label)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error", "warn") else None)
        page.on("pageerror", lambda e: print("[pageerror]", e))

        # 打开画布（含等待 dev hooks 就绪）
        def open_canvas(cid):
            page.evaluate(f"""() => window.__canvas.getState().openCanvas({cid}).then(() => window.__ui.getState().setActive('canvas'))""")
            page.wait_for_selector(".react-flow__viewport", timeout=20000)
            page.wait_for_timeout(700)

        def reload_and_reopen(cid):
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function("() => !!window.__canvas && !!window.__ui", timeout=20000)
            page.wait_for_timeout(400)
            open_canvas(cid)

        # ========== 注册并进入画布 ==========
        page.goto(BASE, wait_until="domcontentloaded"); page.wait_for_timeout(600)
        page.evaluate("localStorage.setItem('__peaDevHooks','1')")
        page.reload(wait_until="domcontentloaded"); page.wait_for_timeout(600)
        page.get_by_role("button", name="没有账号？去注册").first.click(); page.wait_for_timeout(300)
        page.fill('input[placeholder="you@pea.ai"]', EMAIL)
        page.fill('input[placeholder="至少 8 位"]', PW)
        page.fill('input[placeholder="可选"]', "VMF")
        page.locator("form button[type=submit]").click(); page.wait_for_timeout(3500)
        page.wait_for_selector("text=新建项目", timeout=8000)
        page.locator("text=新建项目").first.click(); page.wait_for_timeout(1000)
        page.wait_for_selector(".react-flow__viewport", timeout=20000)
        page.wait_for_timeout(800)

        # 通过 API 创建画布并打开（后续刷新场景复用同一 cid）
        cid = page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/canvases', {method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},body:JSON.stringify({title:'vmf',scope:'personal'})});
            return (await r.json()).id;
        }""")
        open_canvas(cid)

        # ========== 1) 图片节点刷新后发送按钮可用 ==========
        print("\n--- Test 1: image node send button after refresh ---")
        page.evaluate("""() => {
            const s = window.__canvas.getState();
            const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
            const img = mk('nImg','image',300,200,{aspectRatio:'1:1'});
            s.loadGraph([img], [], s.version);
            s.select('nImg');
        }""")
        page.wait_for_timeout(500)
        # 真实输入内容（触发 autosave），而非仅靠 meta.editorText
        page.locator('.node-prompt-editor').fill("a cute cat")
        page.wait_for_timeout(2600)  # 防抖持久化(700) + 画布 autosave(1000) + 缓冲

        # 断言：输入后（刷新前）发送按钮即应可用
        before_refresh = page.evaluate("""() => {
            const editor = document.querySelector('.node-prompt-editor');
            const btn = document.querySelector('.node-input-send');
            return { hasText: editor ? editor.innerText.includes('cute cat') : false, disabled: btn ? btn.disabled : null };
        }""")
        step("图片节点输入后发送按钮可用", before_refresh.get("disabled") is False, str(before_refresh))

        # 刷新 → 重新打开同一画布（服务端已保存 editorText）→ 选中
        reload_and_reopen(cid)
        page.evaluate("""() => { window.__canvas.getState().select('nImg'); }""")
        page.wait_for_timeout(900)
        after_refresh = page.evaluate("""() => {
            const editor = document.querySelector('.node-prompt-editor');
            const btn = document.querySelector('.node-input-send');
            return {
                hasText: editor ? editor.innerText.includes('cute cat') : false,
                disabled: btn ? btn.disabled : null,
            };
        }""")
        step("刷新后图片节点编辑框仍有内容", after_refresh.get("hasText") is True, str(after_refresh))
        step("刷新后图片节点发送按钮可用", after_refresh.get("disabled") is False, str(after_refresh))

        # 断言：刷新/打开节点还原内容后，光标应停在文本末尾而非开头
        caret = page.evaluate("""() => {
            const editor = document.querySelector('.node-prompt-editor');
            if (!editor) return { ok: False, detail: 'no editor' };
            const sel = window.getSelection();
            if (!sel || sel.rangeCount === 0) return { ok: False, detail: 'no selection' };
            const r = sel.getRangeAt(0);
            const total = (editor.textContent || '').length;
            const pre = document.createRange();
            pre.selectNodeContents(editor);
            pre.setEnd(r.startContainer, r.startOffset);
            const offset = pre.toString().length;
            return { ok: r.collapsed && offset === total, offset, total };
        }""")
        step("刷新后打开节点光标停在文本末尾", caret.get("ok") is True, str(caret))

        # ========== 2) 视频节点输入内容后刷新不丢失 ==========
        print("\n--- Test 2: video node input persists after refresh ---")
        page.evaluate("""() => {
            const s = window.__canvas.getState();
            const mk = (id,kind,x,y,extra={}) => ({id,type:'pea',position:{x,y},data:{kind,label:kind,...extra}});
            const vid = mk('nVid','video',300,450,{aspectRatio:'16:9'});
            s.loadGraph([vid], [], s.version);
            s.select('nVid');
        }""")
        page.wait_for_timeout(600)
        page.locator('.node-prompt-editor').fill("a cat walking on a beach")
        page.wait_for_timeout(2600)  # 等待 autosave 落库

        # 刷新 → 重新打开同一画布 → 选中
        reload_and_reopen(cid)
        page.evaluate("""() => { window.__canvas.getState().select('nVid'); }""")
        page.wait_for_timeout(900)
        restored_text = page.evaluate("""() => {
            const editor = document.querySelector('.node-prompt-editor');
            return editor ? editor.innerText : '';
        }""")
        step("刷新后视频节点编辑框内容恢复", "cat walking" in restored_text, f"restored='{restored_text[:60]}'")
        # 恢复内容后发送按钮也应可用
        btn2 = page.evaluate("""() => { const b=document.querySelector('.node-input-send'); return b?b.disabled:null; }""")
        step("刷新后视频节点发送按钮可用", btn2 is False, f"disabled={btn2}")

        # ========== 3) 视频节点连线时显示缩略图且 hover 播放 ==========
        print("\n--- Test 3: video upstream thumbnail & hover preview ---")
        page.evaluate(f"""() => {{
            const s = window.__canvas.getState();
            const mk = (id,kind,x,y,extra={{}}) => ({{id,type:'pea',position:{{x,y}},data:{{kind,label:kind,...extra}}}});
            const vsrc = mk('nVidSrc','video',200,600,{{resultUrl:'{VIDEO_URL}', aspectRatio:'16:9', meta:{{fileName:'bunny.mp4'}}}});
            const itgt = mk('nImgTgt','image',700,600,{{prompt:'', meta:{{}}, aspectRatio:'16:9'}});
            s.loadGraph([vsrc, itgt], [{{id:'ev1',source:'nVidSrc',target:'nImgTgt',type:'pea'}}], s.version);
            s.select('nImgTgt');
        }}""")
        page.wait_for_timeout(1000)
        thumb_info = page.evaluate("""() => {
            const thumb = document.querySelector('.node-ref-thumb[data-ref-kind="video"]');
            const video = document.querySelector('.node-ref-thumb-video');
            return { hasThumb: !!thumb, hasVideo: !!video, videoSrc: video ? video.src : null };
        }""")
        step("视频上游在引用条中显示缩略图", thumb_info.get("hasThumb") is True, str(thumb_info))
        step("视频缩略图使用 video 元素（非问号）", thumb_info.get("hasVideo") is True, str(thumb_info))
        step("video 元素 src 正确", VIDEO_URL in (thumb_info.get("videoSrc") or ""), str(thumb_info))

        # hover 视频缩略图，检查 popover
        if thumb_info.get("hasVideo"):
            page.locator('.node-ref-thumb-video').first.hover(); page.wait_for_timeout(350)
            popover = page.locator('.pea-ref-video-popover')
            step("hover 视频缩略图显示播放浮层", popover.count() > 0, f"popover_count={popover.count()}")
            if popover.count() > 0:
                has_tag = popover.locator('text=@Video').count() > 0
                step("播放浮层包含 @Video 标签", has_tag)

        # ========== 4) 删除连线后缩略图移除 ==========
        print("\n--- Test 4: delete edge removes upstream thumbnail ---")
        page.evaluate("""() => {
            const s = window.__canvas.getState();
            s.removeEdge('ev1');
        }""")
        page.wait_for_timeout(600)
        after_delete = page.evaluate("""() => {
            return {
                thumbCount: document.querySelectorAll('.node-ref-thumb').length,
                videoThumbCount: document.querySelectorAll('.node-ref-thumb-video').length,
            };
        }""")
        step("删除连线后引用条中无视频缩略图", after_delete.get("videoThumbCount") == 0, str(after_delete))

        # 截图
        shots = os.path.dirname(__file__) + '/shots'
        os.makedirs(shots, exist_ok=True)
        page.screenshot(path=f'{shots}/node_media_fixes.png')
        print(f"\n截图保存: {shots}/node_media_fixes.png")

        browser.close()

        if errors:
            print(f"\n❌ 共 {len(errors)} 项失败: {errors}")
            sys.exit(1)
        else:
            print("\n✅ 节点媒体交互修复全部通过!")


if __name__ == '__main__':
    main()
