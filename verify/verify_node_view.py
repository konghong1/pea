import glob, os, sys, math
from PIL import Image
from io import BytesIO
from playwright.sync_api import sync_playwright

ROOT = "D:/workspace/pea"
CSS_DIR = os.path.join(ROOT, "pea-server/web/dist/static")
SAMPLE = os.path.join(ROOT, "verify/shots/node_sample.png")

def make_sample():
    W, H = 280, 360
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            # 彩色对角线渐变 + 中心高对比块，确保亮度非零且稳定
            r = int(120 + 100 * (x / W))
            g = int(80 + 120 * (y / H))
            b = int(160 + 80 * ((x + y) / (W + H)))
            px[x, y] = (r, g, b)
    # 中心画一个亮黄方块，方便肉眼/调试
    for y in range(150, 210):
        for x in range(110, 170):
            px[x, y] = (250, 230, 40)
    img.save(SAMPLE)

def lum(png_bytes):
    im = Image.open(BytesIO(png_bytes)).convert("RGB")
    w, h = im.size
    x, y = w // 2, h // 2
    # 取中心 5x5 平均，降低抗锯齿噪声
    rs = gs = bs = 0
    n = 0
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            r, g, b = im.getpixel((min(max(x + dx, 0), w - 1), min(max(y + dy, 0), h - 1)))
            rs += r; gs += g; bs += b; n += 1
    r, g, b = rs / n, gs / n, bs / n
    return 0.299 * r + 0.587 * g + 0.114 * b

def find_css():
    cands = glob.glob(os.path.join(CSS_DIR, "index-*.css"))
    # 按修改时间取最新构建产物，避免误选上次构建遗留的旧 css
    cands.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    for f in cands:
        with open(f, "r", encoding="utf-8", errors="ignore") as fh:
            if ".pea-node-media-preview" in fh.read():
                return f
    raise SystemExit("node CSS not found in " + CSS_DIR)

def main():
    make_sample()
    css_path = find_css()
    css_url = "file:///" + css_path.replace("\\", "/")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{css_url}">
<style>
  body {{ margin: 0; padding: 40px; font-family: sans-serif; }}
  .stage {{ display: inline-block; padding: 24px; vertical-align: top; }}
  .pea-node {{ width: 280px; }}
  .pea-node .pea-node-body-card {{ width: 280px; height: 360px; }}
  .pea-node-result-image-wrap {{ height: 360px; }}
  .pea-node-media-preview {{ height: 360px; }}
  .pea-gen-demo {{ width: 280px; height: 360px; display:flex; align-items:center; justify-content:center; color:#888; }}
</style></head><body>
<div class="stage" id="st-cine" data-surface="cinematic">
  <h4>cinematic (Runway)</h4>
  <div class="pea-node pea-node-image pea-node-has-media" id="n-cine">
    <div class="pea-node-body-card">
      <div class="pea-node-media-card">
        <div class="pea-node-result-image-wrap">
          <img class="pea-node-media-preview pea-node-result-preview" src="file:///{SAMPLE.replace(chr(92),'/')}">
        </div>
      </div>
    </div>
  </div>
  <div class="pea-node pea-node-image is-generating" id="n-cine-gen">
    <div class="pea-node-body-card"><div class="pea-gen-demo">generating…</div></div>
  </div>
</div>

<div class="stage dark" id="st-dark">
  <h4>precision dark</h4>
  <div class="pea-node pea-node-image pea-node-has-media" id="n-dark">
    <div class="pea-node-body-card">
      <div class="pea-node-media-card">
        <div class="pea-node-result-image-wrap">
          <img class="pea-node-media-preview pea-node-result-preview" src="file:///{SAMPLE.replace(chr(92),'/')}">
        </div>
      </div>
    </div>
  </div>
</div>

<div class="stage" id="st-light">
  <h4>precision light</h4>
  <div class="pea-node pea-node-image pea-node-has-media" id="n-light">
    <div class="pea-node-body-card">
      <div class="pea-node-media-card">
        <div class="pea-node-result-image-wrap">
          <img class="pea-node-media-preview pea-node-result-preview" src="file:///{SAMPLE.replace(chr(92),'/')}">
        </div>
      </div>
    </div>
  </div>
</div>
</body></html>"""

    harness = os.path.join(ROOT, "verify/shots/node_harness.html")
    with open(harness, "w", encoding="utf-8") as fh:
        fh.write(html)

    results = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 800})
        pg.goto("file:///" + harness.replace("\\", "/"))
        pg.wait_for_timeout(400)

        nodes = ["n-cine", "n-dark", "n-light"]
        for nid in nodes:
            img = pg.locator(f"#{nid} .pea-node-media-preview")
            img.wait_for(state="visible")
            base = lum(img.screenshot())
            # hover 序列
            pg.locator(f"#{nid}").hover()
            hover_lums = []
            for _ in range(4):
                pg.wait_for_timeout(150)
                hover_lums.append(lum(img.screenshot()))
            # 选中
            pg.evaluate(f"document.getElementById('{nid}').classList.add('selected')")
            sel_lums = []
            for _ in range(4):
                pg.wait_for_timeout(150)
                sel_lums.append(lum(img.screenshot()))
            op = pg.evaluate(f"getComputedStyle(document.querySelector('#{nid} .pea-node-media-preview')).opacity")
            flt = pg.evaluate(f"getComputedStyle(document.querySelector('#{nid} .pea-node-media-preview')).filter")
            # 选中态边框色（应为 AI 紫）
            bcol = pg.evaluate(f"getComputedStyle(document.querySelector('#{nid} .pea-node-body-card')).borderTopColor")
            max_delta = max([abs(v - base) for v in hover_lums + sel_lums])
            ok = max_delta < 4 and op == "1" and flt == "none"
            results.append((nid, base, hover_lums, sel_lums, op, flt, bcol, max_delta, ok))
            print(f"[{nid}] base={base:.1f} hover={[f'{v:.1f}' for v in hover_lums]} sel={[f'{v:.1f}' for v in sel_lums]} opacity={op} filter={flt} border={bcol} maxΔ={max_delta:.2f} {'PASS' if ok else 'FAIL'}")

        # 生成态动画应存在；非生成态应无动画
        gen_anim = pg.evaluate("getComputedStyle(document.getElementById('n-cine-gen')).animationName")
        gen_cls = pg.evaluate("document.getElementById('n-cine-gen').classList.contains('is-generating')")
        nongen_anim = pg.evaluate("getComputedStyle(document.getElementById('n-cine')).animationName")
        print(f"[gen] is-generating={gen_cls} animationName={gen_anim}  | [normal] animationName={nongen_anim}")
        gen_ok = (gen_anim != "none") and (nongen_anim == "none")
        results.append(("gen", gen_anim, nongen_anim, gen_ok))
        # 视觉证明：选中态（紫环）+ 生成态截图
        pg.locator("#n-cine").screenshot(path=os.path.join(ROOT, "verify/shots/node_proof_selected.png"))
        pg.locator("#n-cine-gen").screenshot(path=os.path.join(ROOT, "verify/shots/node_proof_generating.png"))
        b.close()

    all_ok = all(r[-1] for r in results)
    print("\n=== SUMMARY ===")
    print("IMAGE STABILITY (hover/select must not change pixel luminance):",
          "PASS" if all_ok else "FAIL")
    print("SELECTED BORDER must be AI purple (rgb(139,92,246) or rgb(167,139,250)):",
          all(('139, 92, 246' in r[6]) or ('167, 139, 250' in r[6]) for r in results if r[0] in nodes))
    print("GENERATING animation present, normal node static:",
          "PASS" if gen_ok else "FAIL")
    sys.exit(0 if all_ok and gen_ok else 1)

if __name__ == "__main__":
    main()
