# -*- coding: utf-8 -*-
"""诊断：AI 图 vs 上传图 的替换按钮 + 重新进入后加载/按钮状态"""
from __future__ import annotations
import pathlib, tempfile, os
from playwright.sync_api import sync_playwright

WEB = "http://localhost:8088"
IMG = "https://picsum.photos/seed/peatest/400/300"

def main():
    errors = []
    def step(label, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {label}  {detail}")
        if not ok: errors.append(label)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        page = ctx.new_page()
        page.on("console", lambda m: print("[console]", m.type, m.text[:150]) if m.type in ("error",) else None)

        page.goto(WEB, wait_until="networkidle")
        ts = page.evaluate("Date.now()")
        email = f"diag_{ts}@pea.ai"
        if page.locator("text=去注册").count() > 0:
            page.locator("text=去注册").first.click(); page.wait_for_timeout(500)
        ins = page.locator("input:visible"); cnt = ins.count()
        if cnt >= 2:
            ins.nth(0).fill(email); page.wait_for_timeout(120)
            ins.nth(1).fill("test1234"); page.wait_for_timeout(120)
            if cnt >= 3: ins.nth(2).fill("Diag")
        page.locator("button", has_text="注").first.click(); page.wait_for_timeout(1500)
        page.wait_for_selector("text=新建项目", timeout=8000)
        page.locator("text=新建项目").first.click(); page.wait_for_timeout(900)
        page.wait_for_selector(".react-flow", timeout=10000); page.wait_for_timeout(400)

        def add_node(label):
            page.locator(".pea-tlb-btn[aria-label*='添加节点']").first.click(); page.wait_for_timeout(250)
            page.locator(f".pea-add-menu-item:has-text('{label}')").first.click(); page.wait_for_timeout(350)
            return page.evaluate("""() => { const s=window.__canvas.getState(); const ns=s.nodes; return ns[ns.length-1].id; }""")

        # AI image node
        a = add_node("图片")
        page.evaluate("""(args)=>{ const [id,url]=args; window.__canvas.getState().updateNodeData(id,{ resultUrls:[url], resultUrl:url, resultIndex:0, generating:false }); }""", [a, IMG])
        page.wait_for_timeout(500)
        # Uploaded image node (real file -> blob url)
        b = add_node("图片")
        # make a tiny local png
        tmp = os.path.join(tempfile.gettempdir(), "pea_up.png")
        with open(tmp, "wb") as f:
            f.write(__import__("base64").b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="))
        finput = page.locator(f'.react-flow__node[data-id="{b}"] input[type=file]')
        finput.set_input_files(tmp)
        page.wait_for_timeout(800)
        b_url = page.evaluate("""(id)=>{ const n=window.__canvas.getState().nodes.find(n=>n.id===id); return n.data.url; }""", b)

        def inspect(nid, label):
            info = page.evaluate("""(id) => {
              const wrap = document.querySelector('.react-flow__node[data-id="'+id+'"]');
              if (!wrap) return {found:false};
              const btns = Array.from(wrap.querySelectorAll('.pea-node-result-replace'));
              const img = wrap.querySelector('img.pea-node-media-preview');
              return {
                found:true,
                replaceCount: btns.length,
                btnText: btns.map(b=>b.textContent.trim()),
                btnOpacity: btns.map(b=>getComputedStyle(b).opacity),
                imgSrc: img ? img.getAttribute('src')?.slice(0,40) : null,
                imgNatural: img ? img.naturalWidth : null,
              };
            }""", nid)
            print(f"  {label} ({nid}):", info)
            return info

        print("=== 首次进入 ===")
        ia = inspect(a, "AI-image"); ib = inspect(b, "Uploaded")
        step("AI 图有替换按钮", ia.get("replaceCount",0) == 1, str(ia.get("btnText")))
        step("上传图有替换按钮", ib.get("replaceCount",0) == 1, str(ib.get("btnText")))
        step("上传图 url 是 blob", str(b_url).startswith("blob:"), f"url={str(b_url)[:30]}")

        # 保存并返回 -> 重新进入
        print("=== 保存并返回，重新进入 ===")
        # 触发保存：调用 store flush (通过 dev hook 不可用, 用返回触发 CanvasEditor flushSave)
        page.evaluate("window.__ui.getState().setActive('workspace')")
        page.wait_for_timeout(1500)
        page.locator(".projects-card[data-canvas-id]").first.click(); page.wait_for_timeout(1800)

        print("=== 重新进入后 ===")
        ia2 = inspect(a, "AI-image(after)"); ib2 = inspect(b, "Uploaded(after)")
        step("AI 图重进后仍加载(opacity/图)", ia2.get("found") and ia2.get("replaceCount",0)==1, str(ia2.get("imgNatural")))
        step("上传图重进后是否还能加载", (ib2.get("imgNatural") or 0) > 0, f"natural={ib2.get('imgNatural')} src={ib2.get('imgSrc')}")

        browser.close()

    print("\n结论:", "全部通过 ✅" if not errors else f"失败项: {errors}")

if __name__ == "__main__":
    main()
