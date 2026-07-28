"""截图：节点生成失败卡（科技风 redesign）"""
import os
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8088"
HERE = Path(__file__).parent
SHOTS = HERE / "shots" / "image_failure"
SHOTS.mkdir(parents=True, exist_ok=True)
OUT = SHOTS / "failure-card-redesign.png"


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
                                     args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.add_init_script("localStorage.setItem('__peaDevHooks','1')")

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

        cid = page.evaluate("""async () => {
            const token = localStorage.getItem('pea_token');
            const r = await fetch('/canvases', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'Authorization': `Bearer ${token}`},
                body: JSON.stringify({name: 'failure-screenshot', description: ''})
            });
            const j = await r.json();
            return j.id || j.data?.id;
        }""")
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(800)

        page.evaluate("""async (cid) => {
            const store = window.__canvas;
            await store.getState().openCanvas(cid);
            const mk = (id, kind, x, y, extra={}) =>
                ({id, type:'pea', position:{x,y}, data:{kind,label:kind,...extra}});
            store.setState({
              nodes: [
                mk('nImg','image',420,200,{
                    prompt:'科技感城市夜景',
                    resultUrl:'https://old.example/x.png',
                    resultUrls:['https://old.example/x.png'],
                    error:undefined,
                    generating:false,
                    meta:{modelId:'agnes-flash'}
                })
              ],
              edges: [], version: 1, dirty: true,
            });
            store.getState().select('nImg');
            window.__ui.getState().setActive('canvas');
            await new Promise(r => setTimeout(r, 200));
            store.getState().registerJob('job-fail-001', 'nImg');
            store.getState().applyJobResult('job-fail-001', {
                generating: false,
                error: '上游接口返回异常，已自动退款。可稍后再试。',
                resultUrl: undefined,
                resultUrls: undefined,
                resultIndex: 0,
                savedToLibrary: false,
            });
            store.getState().removeJob('job-fail-001');
        }""", cid)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT), full_page=False)
        print(f"截图已保存: {OUT}")
        browser.close()


if __name__ == "__main__":
    main()
