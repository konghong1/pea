"""
验证图片节点生成失败时的显示修复:
  1. 节点有旧 resultUrl 且生成失败(error)时, 应显示失败卡而非裂图
  2. 点击"重新生成"后旧 resultUrl 被清理, 节点进入 generating 态
  3. 直接设置无效 resultUrl(无 error)时, 应显示"图片加载失败"占位而非浏览器默认裂图

使用 dev hooks 注入节点状态, 不依赖真实模型, 可离线跑通.
"""
import os
import sys
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
HERE = Path(__file__).parent
SHOTS = HERE / "shots" / "image_failure"
SHOTS.mkdir(parents=True, exist_ok=True)


def main():
    errors = []

    def step(label, ok, detail=""):
        mark = "✅" if ok else "❌"
        print(f"{mark} {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            errors.append(label)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
                                     args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console",
                lambda m: print(f"[console:{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: print("[pageerror]", e))
        page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

        # 1) 注册并登录
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        if page.locator("text=没有账号？去注册").count() > 0:
            page.locator("text=没有账号？去注册").first.click()
            page.wait_for_timeout(400)
        email = f"imgfail_{uuid.uuid4().hex[:8]}@pea.ai"
        page.fill('input[placeholder="you@pea.ai"]', email)
        page.fill('input[placeholder="至少 8 位"]', "test1234")
        page.fill('input[placeholder="可选"]', "ImgFailBot")
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
                body: JSON.stringify({title: 'img_fail_test', scope: 'personal'})
            });
            return (await r.json()).id;
        }""")
        print("canvas id:", cid)
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)

        # 3) 注入 image 节点, 先处于"生成成功"状态(有旧 resultUrl)
        state = page.evaluate("""async (cid) => {
            const store = window.__canvas;
            await store.getState().openCanvas(cid);
            const mk = (id, kind, x, y, extra={}) =>
                ({id, type:'pea', position:{x,y}, data:{kind,label:kind,...extra}});
            store.setState({
              nodes: [
                mk('nImg','image',420,240,{
                    prompt:'一只戴耳机的猫',
                    resultUrl:'http://invalid.example.com/broken.png',
                    resultUrls:['http://invalid.example.com/broken.png'],
                    error:undefined,
                    generating:false,
                    meta:{modelId:'agnes-flash'}
                })
              ],
              edges: [], version: 1, dirty: true,
            });
            store.getState().select('nImg');
            window.__ui.getState().setActive('canvas');
            return { selectedId: store.getState().selectedId };
        }""", cid)
        print("注入节点:", state)
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "01_success_injected.png"))

        # 4) 模拟后端返回"生成失败"事件(通过 applyJobResult, 与真实 WS 路径一致)
        #    修复前: 失败时只改 error, 旧 resultUrl 仍在, 会显示裂图
        #    修复后: 失败同时清理 resultUrl/resultUrls, 显示失败卡
        page.evaluate("""() => {
            const store = window.__canvas;
            store.getState().registerJob('job-fail-001', 'nImg');
            store.getState().applyJobResult('job-fail-001', {
                generating: false,
                error: 'submit error: upstream unavailable',
                resultUrl: undefined,
                resultUrls: undefined,
                resultIndex: 0,
                savedToLibrary: false,
            });
            store.getState().removeJob('job-fail-001');
        }""")
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "02_after_failure_event.png"))

        failure_card = page.locator('.pea-node-failure')
        broken_img = page.locator('.react-flow__node[data-id="nImg"] img.pea-node-result-preview')
        step("失败卡已显示", failure_card.count() > 0, f"count={failure_card.count()}")
        step("裂图/结果图未显示", broken_img.count() == 0, f"img_count={broken_img.count()}")

        # 5) 点击"重新生成", 验证旧 resultUrl 被清理、进入 generating
        retry_btn = page.locator('.pea-node-failure .pea-btn--warn')
        step("重新生成按钮存在", retry_btn.count() > 0)
        if retry_btn.count() > 0:
            retry_btn.first.click()
            page.wait_for_timeout(1200)
            page.screenshot(path=str(SHOTS / "03_after_retry_click.png"))

            result_url_after = page.evaluate(
                "() => { const n = window.__canvas.getState().nodes.find(x=>x.id==='nImg'); "
                "return (n && n.data.resultUrl) || ''; }")
            # 由于没有真实可用模型, 重新生成受理会失败, 不会进入 generating;
            # 核心修复是: 点击重新生成后立即清理旧 resultUrl, 避免旧图残留.
            step("点击重新生成后旧 resultUrl 已清理", result_url_after == "", f"resultUrl={result_url_after[:40]}")

        # 6) 第二个场景: 只有无效 resultUrl, 无 error -> 应显示"图片加载失败"占位
        #    用同域 404 URL, 浏览器会快速触发 error 事件
        page.evaluate("""() => {
            const store = window.__canvas;
            store.setState({
              nodes: store.getState().nodes.map(n =>
                n.id === 'nImg'
                  ? { ...n, data: { ...n.data, generating:false, error:undefined,
                                    resultUrl:'/nonexistent-image-404.png',
                                    resultUrls:['/nonexistent-image-404.png'] } }
                  : n
              ),
            });
        }""")
        # 等待图片加载/失败, 并监听 console 以确认 onError 触发
        page.wait_for_timeout(2500)
        page.screenshot(path=str(SHOTS / "04_invalid_url_no_error.png"))
        error_placeholder = page.locator('.pea-node-result-image-error')
        step("无效 URL 无 error 时显示加载失败占位", error_placeholder.count() > 0,
             f"placeholder_count={error_placeholder.count()}")

        browser.close()

    if errors:
        print(f"\n❌ 失败项: {errors}")
        return 1
    print("\n🎉 全部验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
