"""
验证图片节点 @ 引用相关的 4 个问题修复:
  1. 图片节点 @ 列表中不出现连接的文本节点 (canReferenceForKind 过滤)
  2. 第一次 @ 显示图片，重新打开 / 已插入 token 仍能展示 (缩略图用签名 URL 且随媒体源变化刷新)
  3. @ 一个图片后，再次使用 @ 图片列表仍能正常弹出 (picker 触发逻辑 / zwsp 边界)
  4. @ 图片发送后，请求 params.reference_images 包含上传图签名 URL (getParsed + param_adapters)

场景：注入“文本上游节点 nText” + “图片上游节点 nImgSrc” 都连接到图片宿主节点 nImg。
图片节点按设计只引用媒体节点，因此 picker 应出现 nImgSrc 但不出现 nText（问题1）。
"""
import os
import sys
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
HERE = Path(__file__).parent
SHOTS = HERE / "shots" / "ref_issues"
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
    captured = {}

    def capture_req(req):
        if "/generation" in req.url:
            try:
                body = req.post_data_json
                print(f"  [req] {req.method} {req.url}  body_ok={body is not None}")
                if body:
                    captured["body"] = body
                    params = body.get("params") or {}
                    print(f"  捕获 /generation/node: model={body.get('model')} "
                          f"refs={params.get('reference_images')}")
            except Exception as e:
                print(f"  解析请求失败: {e}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
                                     args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console",
                lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: print("[pageerror]", e))
        page.on("request", capture_req)
        page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

        # 1) 注册并登录
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        if page.locator("text=没有账号？去注册").count() > 0:
            page.locator("text=没有账号？去注册").first.click()
            page.wait_for_timeout(400)
        email = f"ref_{uuid.uuid4().hex[:8]}@pea.ai"
        page.fill('input[placeholder="you@pea.ai"]', email)
        page.fill('input[placeholder="至少 8 位"]', "test1234")
        page.fill('input[placeholder="可选"]', "RefBot")
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
                body: JSON.stringify({title: 'ref_test', scope: 'personal'})
            });
            return (await r.json()).id;
        }""")
        print("canvas id:", cid)
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)

        # 3) 注入节点
        state = page.evaluate("""async (cid) => {
            const store = window.__canvas;
            await store.getState().openCanvas(cid);
            const mk = (id, kind, x, y, extra={}) =>
                ({id, type:'pea', position:{x,y}, data:{kind,label:kind,...extra}});
            store.setState({
              nodes: [
                mk('nText','text',120,120,{html:'生成一只猫', prompt:'生成一只猫'}),
                mk('nImgSrc','image',120,360,{html:'',prompt:'',meta:{}}),
                mk('nImg','image',420,240,{html:'',prompt:'',meta:{}})
              ],
              edges: [], version: 1, dirty: true,
            });
            store.getState().onConnect({source:'nText', target:'nImg'});
            store.getState().onConnect({source:'nImgSrc', target:'nImg'});
            store.getState().select('nImg');
            window.__ui.getState().setActive('canvas');
            return { selectedId: store.getState().selectedId,
                     nodes: store.getState().nodes.length,
                     edges: store.getState().edges.length };
        }""", cid)
        print("注入节点:", state)
        page.wait_for_timeout(1200)

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
            page.screenshot(path=str(SHOTS / "after_upload_src.png"))
        else:
            step("上传后 nImgSrc 获得 fileKey", False, "文件输入不存在")

        def focus_editor():
            """确保 nImg 被选中且编辑器挂载，返回编辑器 locator。"""
            page.locator('.react-flow__node[data-id="nImg"]').click()
            page.wait_for_timeout(300)
            ed = page.locator(".node-prompt-editor").first
            ed.click()
            page.wait_for_timeout(150)
            return ed

        # 5) 第一次 @：验证问题1 + 缩略图
        ed = focus_editor()
        page.keyboard.type("@")
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "picker_open_first.png"))

        step("图片节点 @ picker 已弹出", page.locator(".pea-ref-picker").count() > 0)
        item_count = page.locator(".pea-ref-picker-item").count()
        text_item_count = page.locator(".pea-ref-picker-item:has-text('生成一只猫')").count()
        step("@ 列表出现图片项", item_count > 0, f"item_count={item_count}")
        step("图片节点 @ 列表不包含文本节点", text_item_count == 0, f"text_item_count={text_item_count}")

        # 等待缩略图解析（resolvedThumbs 用签名 URL）
        thumb_ok = False
        for _ in range(25):
            if page.locator(".pea-ref-picker-thumb").count() > 0:
                thumb_ok = True
                break
            page.wait_for_timeout(400)
        step("picker 缩略图为真实图片(非占位)", thumb_ok)
        # 诊断：打印 picker 缩略图真实 src
        if thumb_ok:
            tsrc = page.locator(".pea-ref-picker-thumb").first.get_attribute("src") or ""
            print(f"  [diag] picker 缩略图 src = {tsrc[:160]}")
        page.screenshot(path=str(SHOTS / "picker_first_thumb.png"))

        # 6) 选择第一张图片
        if item_count > 0:
            page.locator(".pea-ref-picker-item").first.click()
            page.wait_for_timeout(600)
        page.screenshot(path=str(SHOTS / "after_first_ref.png"))

        token_imgs = page.locator(".node-prompt-editor .pea-ref-thumb")
        step("已插入图片 token", token_imgs.count() > 0, f"count={token_imgs.count()}")
        if token_imgs.count() > 0:
            tok_html = token_imgs.first.evaluate("el => el.outerHTML")
            print(f"  [diag] token outerHTML = {tok_html[:240]}")
        token_src = token_imgs.first.get_attribute("src") or "" if token_imgs.count() > 0 else ""
        # 显示用 URL 可为 http(s) 直链或同源 BFF 代理的 blob: URL（均能在浏览器渲染）
        step("已插入 token 缩略图可渲染(http/blob)", token_src.startswith("http") or token_src.startswith("blob:"),
             f"src={token_src[:60]}..." if token_src else "src=空")

        # 7) 问题2：重新打开 picker，缩略图仍能展示
        ed = focus_editor()
        page.keyboard.press("End")
        page.wait_for_timeout(150)
        page.keyboard.type("@")
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "picker_reopen.png"))
        reopen_thumb = page.locator(".pea-ref-picker-thumb").count() > 0
        step("重新打开 picker 仍能展示图片缩略图", reopen_thumb)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 8) 问题3：再次 @ 列表仍能弹出
        ed = focus_editor()
        page.keyboard.press("End")
        page.wait_for_timeout(150)
        page.keyboard.type("@")
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "picker_second_at.png"))
        step("再次 @ 后 picker 仍能弹出", page.locator(".pea-ref-picker").count() > 0)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 9) 输入文本并发送
        ed = focus_editor()
        page.keyboard.press("End")
        page.keyboard.type(" 放在猫的旁边")
        page.wait_for_timeout(300)

        chip = page.locator(".node-input-model-chip")
        ctext = chip.first.text_content() or "" if chip.count() > 0 else "(no chip)"
        print(f"  [diag] model chip text = {ctext!r}")
        # 总是打开模型选择器，挑选第一个「未锁定」的模型，确保可发起生成
        # （默认模型可能对该免费账号锁定，导致 submit 提前 return、不发请求）。
        if chip.count() > 0:
            chip.first.click()
            try:
                page.wait_for_selector(".node-model-picker", timeout=5000)
                cards = page.locator(".picker-card")
                print(f"  [diag] model picker cards = {cards.count()}")
                picked = False
                for i in range(cards.count()):
                    locked = cards.nth(i).locator(".picker-card-lock-hint").count() > 0
                    name = cards.nth(i).locator(".picker-card-name").text_content() or ""
                    print(f"  [diag]   card[{i}] {name!r} locked={locked}")
                    if not locked:
                        cards.nth(i).click()
                        picked = True
                        break
                if not picked and cards.count() > 0:
                    cards.first.click()
                page.wait_for_timeout(500)
            except Exception as e:
                print(f"  [diag] 打开模型选择器失败: {e}")

        page.screenshot(path=str(SHOTS / "before_send.png"))
        send_btn = page.locator("button.node-input-send")
        step("发送按钮存在", send_btn.count() > 0, f"count={send_btn.count()}")
        if send_btn.count() > 0:
            send_btn.first.click()
            page.wait_for_timeout(1800)

        # 10) 问题4：检查 /generation/node 请求
        body = captured.get("body", {})
        refs = (body.get("params") or {}).get("reference_images")
        step("请求包含 reference_images", bool(refs) and isinstance(refs, list) and len(refs) > 0,
             f"refs={refs}")
        if refs:
            first_ref = refs[0]
            step("参考图 URL 为 http(s) 签名地址",
                 isinstance(first_ref, str) and first_ref.startswith("http"),
                 f"url={first_ref[:100]}...")

        page.wait_for_timeout(2000)
        page.screenshot(path=str(SHOTS / "final.png"))
        browser.close()

    if errors:
        print(f"\n❌ 失败项: {errors}")
        return 1
    print("\n🎉 全部验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
