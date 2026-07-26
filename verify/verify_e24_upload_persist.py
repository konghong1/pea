# -*- coding: utf-8 -*-
"""E24：上传的图/视频持久化（整页刷新后仍可加载）+ AI 图替换按钮在刷新后仍在。

  复现用户反馈：
   - 自己上传的图片/视频，下一次点进去就加载不出来（旧实现用 blob: URL，刷新即失效）。
   - 修复：上传直传 MinIO，存 fileKey，渲染时解析签名 URL（持久）。
  同时复核：AI 生成图片的「替换」按钮在整页刷新后依然存在。
"""
from __future__ import annotations
import os, tempfile, base64
from playwright.sync_api import sync_playwright

WEB = "http://localhost:8088"
IMG_EXT = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

def main():
    errors = []
    def step(label, ok, detail=""):
        print(f"[{'PASS' if ok else 'FAIL'}] {label}  {detail}")
        if not ok: errors.append(label)

    # 本地小图（用作“上传”文件）
    tmp = os.path.join(tempfile.gettempdir(), "pea_up_e24.png")
    with open(tmp, "wb") as f:
        f.write(base64.b64decode(IMG_EXT))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("window.__peaDevHooks = 1;")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"console:{m.type}:{m.text[:120]}") if m.type == "error" else None)

        page.goto(WEB, wait_until="networkidle")
        ts = page.evaluate("Date.now()")
        email = f"e24_{ts}@pea.ai"
        if page.locator("text=去注册").count() > 0:
            page.locator("text=去注册").first.click(); page.wait_for_timeout(500)
        ins = page.locator("input:visible"); cnt = ins.count()
        if cnt >= 2:
            ins.nth(0).fill(email); page.wait_for_timeout(120)
            ins.nth(1).fill("test1234"); page.wait_for_timeout(120)
            if cnt >= 3: ins.nth(2).fill("E24")
        page.locator("button", has_text="注").first.click(); page.wait_for_timeout(1500)
        page.wait_for_selector("text=新建项目", timeout=8000)
        page.locator("text=新建项目").first.click(); page.wait_for_timeout(900)
        page.wait_for_selector(".react-flow", timeout=10000); page.wait_for_timeout(400)

        def add_node(label):
            page.locator(".pea-tlb-btn[aria-label*='添加节点']").first.click(); page.wait_for_timeout(250)
            page.locator(f".pea-add-menu-item:has-text('{label}')").first.click(); page.wait_for_timeout(350)
            return page.evaluate("""() => { const s=window.__canvas.getState(); const ns=s.nodes; return ns[ns.length-1].id; }""")

        # 上传图节点
        up = add_node("图片")
        page.locator(f'.react-flow__node[data-id="{up}"] input[type=file]').set_input_files(tmp)
        page.wait_for_timeout(1500)  # 等上传 + 解析

        # 注入 AI 图节点（image 节点带 resultUrl）
        ai = add_node("图片")
        page.evaluate("""(id)=>{ window.__canvas.getState().updateNodeData(id,{ resultUrls:['https://picsum.photos/seed/ai24/400/300'], resultUrl:'https://picsum.photos/seed/ai24/400/300', resultIndex:0, generating:false }); }""", ai)
        page.wait_for_timeout(600)

        # 注入 generate 节点（AI 生成节点，通过 AgentPanel 的“生成图片”或手动添加）——验证其结果图也有替换按钮
        gen = page.evaluate("""() => {
          const s = window.__canvas.getState();
          s.addNode({ kind: 'generate', label: '生成', prompt: 'test', resultUrl: 'https://picsum.photos/seed/gen24/400/300', generating: false }, { x: 400, y: 200 });
          const ns = s.nodes;
          return ns[ns.length - 1].id;
        }""")
        page.wait_for_timeout(600)

        # 检查上传节点：fileKey 已落库（非 blob），url 解析为服务端地址
        up_data = page.evaluate("""(id)=>{ const n=window.__canvas.getState().nodes.find(n=>n.id===id); return { url:n.data.url, fileKey:n.data.fileKey }; }""", up)
        step("上传节点存 fileKey（非 blob）", bool(up_data.get("fileKey")) and not str(up_data.get("url","")).startswith("blob:"),
             f"url={str(up_data.get('url'))[:30]} fileKey={up_data.get('fileKey')}")

        # 等自动保存落地
        page.wait_for_timeout(1500)

        # === 整页刷新（杀掉 blob 会话 + 重新加载）===
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(800)
        # 回到工作空间后重新打开项目
        page.wait_for_selector(".projects-card[data-canvas-id]", timeout=8000)
        page.locator(".projects-card[data-canvas-id]").first.click()
        page.wait_for_selector(".react-flow", timeout=10000)
        page.wait_for_timeout(1500)

        def inspect(nid, label):
            return page.evaluate("""(id) => {
              const wrap = document.querySelector('.react-flow__node[data-id="'+id+'"]');
              if (!wrap) return {found:false};
              const btn = wrap.querySelector('.pea-node-result-replace');
              const img = wrap.querySelector('img.pea-node-media-preview');
              return {
                found:true,
                replace: !!btn,
                btnOpacity: btn ? getComputedStyle(btn).opacity : null,
                imgNatural: img ? img.naturalWidth : null,
                imgSrc: img ? (img.getAttribute('src')||'').slice(0,40) : null,
              };
            }""", nid)

        up_after = inspect(up, "上传图(刷新后)")
        ai_after = inspect(ai, "AI图(刷新后)")
        gen_after = inspect(gen, "generate节点(刷新后)")
        step("上传图刷新后仍能加载", (up_after.get("imgNatural") or 0) > 0, f"natural={up_after.get('imgNatural')} src={up_after.get('imgSrc')}")
        step("上传图刷新后仍有替换按钮", up_after.get("replace") is True and float(up_after.get("btnOpacity") or 0) > 0.9, str(up_after))
        step("AI图刷新后仍能加载", (ai_after.get("imgNatural") or 0) > 0, f"natural={ai_after.get('imgNatural')}")
        # AI 图不再有替换按钮（只有上传图才有）
        step("AI图刷新后无替换按钮（符合新需求）", ai_after.get("replace") is not True, str(ai_after))
        step("generate节点刷新后仍能加载", (gen_after.get("imgNatural") or 0) > 0, f"natural={gen_after.get('imgNatural')}")
        step("generate节点刷新后无替换按钮（符合新需求）", gen_after.get("replace") is not True, str(gen_after))

        # 截图
        os.makedirs("verify/shots", exist_ok=True)
        page.screenshot(path="verify/shots/e24_after_reload.png")
        browser.close()

    print("\nconsole errors:", [e for e in errors if e.startswith('console')])
    print("结论:", "全部通过 ✅" if not [e for e in errors if not e.startswith('console')] and not [e for e in errors if e.startswith('console')] else f"失败/异常: {errors}")
    if errors:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
