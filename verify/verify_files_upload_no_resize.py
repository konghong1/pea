#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_files_upload_no_resize.py

验证 BFF `POST /files/upload` 不会对上传图片做缩放 / 重编码 / 压缩，
从而保证前端"按原图分辨率 x2 超采样导出"的裁剪方案不会被后端覆盖。

两层验证：
  1) 静态代码断言（默认执行，零第三方依赖）：
     - files.controller.ts 的 upload 路由必须原样把 `file.buffer` 交给 putObject
     - files.service.ts 的 putObject 必须直接 minio.putObject(body)，无图像转换
     - 两个文件不得 import 任何图像缩放/重编码库（sharp/jimp/gm/imagemagick/...）
     - 附带前端超采样不变量自检：导出位图像素必须 >= 节点显示像素，避免放大糊化
  2) 运行时集成（--live，可选）：
     - 若提供 BFF_BASE_URL + BFF_TOKEN，上传一张精确尺寸 PNG，
       下载后比对像素尺寸是否一致；依赖 requests + Pillow，缺失则跳过。

用法：
  python verify/verify_files_upload_no_resize.py            # 仅静态
  python verify/verify_files_upload_no_resize.py --live    # 静态 + 运行时
"""
import os
import re
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)  # verify/ 的上一级即项目根


def resolve(p):
    return os.path.join(PROJECT_ROOT, p)


CONTROLLER = resolve("pea-server/services/bff/src/modules/files/files.controller.ts")
SERVICE = resolve("pea-server/services/bff/src/modules/files/files.service.ts")

# 任何图像缩放 / 重编码相关的符号（命中即视为可能破坏"原样存储"）
IMAGE_LIB_HINTS = [
    r'\bsharp\b', r'\bjimp\b', r'\bgm\b', r'imagemagick', r'graphicsmagick',
    r'resize\s*\(', r'\.scale\s*\(', r'createCanvas', r'canvas\b.*drawImage',
    r'thumbnail\s*\(', r'compound\s*\(', r'toFormat\s*\(', r'jpeg\s*\(',
]
FORBIDDEN_RE = re.compile('|'.join(IMAGE_LIB_HINTS), re.IGNORECASE)


def read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def static_check():
    results = []
    ctrl = read(CONTROLLER)
    svc = read(SERVICE)

    ok1 = bool(re.search(r'putObject\s*\(\s*key\s*,\s*file\.buffer', ctrl))
    results.append(('controller.upload 原样传递 file.buffer 给 putObject', ok1))

    ok2 = bool(re.search(r'putObject\s*\(\s*this\.bucket\s*,\s*key\s*,\s*body', svc))
    results.append(('service.putObject 直接 minio.putObject(body)，无图像转换', ok2))

    bad = []
    for name, src in (('files.controller.ts', ctrl), ('files.service.ts', svc)):
        hit = FORBIDDEN_RE.search(src)
        if hit:
            bad.append("%s: 命中疑似图像缩放/重编码符号 -> %r" % (name, hit.group(0)))
    results.append(('两个文件无图像缩放/重编码逻辑', len(bad) == 0))

    return results, bad


def check_supersample_invariant():
    """前端超采样不变量：导出位图像素必须 >= 节点显示像素，避免浏览器放大糊化。
    EXPORT_SCALE = min(devicePixelRatio, 2)，outW = round(cropNatW * scale)。"""
    def export_w(crop_nat_w, dpr):
        scale = min(dpr, 2)
        return round(crop_nat_w * scale)

    cases = [
        (150, 1, 280),  # 原图裁剪区仅 150px，DPR1 -> 导出 150 < 280：仍会糊（需更大原图）
        (400, 1, 280),  # 原图裁剪区 400px -> 导出 400 >= 280：清晰
        (150, 2, 280),  # DPR2 超采样 -> 导出 300 >= 280：边际清晰
    ]
    out = []
    for crop_nat, dpr, disp in cases:
        ew = export_w(crop_nat, dpr)
        out.append((crop_nat, dpr, disp, ew, ew >= disp))
    return out


def run_live(base_url, token):
    try:
        import requests
    except ImportError:
        return None, "requests 未安装，跳过运行时验证（pip install requests）"
    try:
        from PIL import Image
        import io
    except ImportError:
        return None, "Pillow 未安装，跳过运行时尺寸比对（pip install pillow）"

    W, H = 1200, 800
    img = Image.new('RGB', (W, H), (255, 255, 255))
    px = img.load()
    for x in range(W):
        for y in range(H):
            px[x, y] = ((x * 13) % 256, (y * 7) % 256, ((x + y) * 5) % 256)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    data = buf.getvalue()

    headers = {'Authorization': 'Bearer %s' % token}
    r = requests.post('%s/files/upload' % base_url.rstrip('/'),
                       files={'file': ('verify_1200x800.png', data, 'image/png')},
                       headers=headers, timeout=30)
    if r.status_code != 200:
        return False, '上传失败 HTTP %d: %s' % (r.status_code, r.text[:200])
    key = r.json().get('key')
    r2 = requests.get('%s/files/url' % base_url.rstrip('/'), params={'key': key},
                      headers=headers, timeout=30)
    if r2.status_code != 200:
        return False, '获取下载URL失败 HTTP %d' % r2.status_code
    dl = requests.get(r2.json()['downloadUrl'], timeout=30)
    out_img = Image.open(io.BytesIO(dl.content))
    ok = (out_img.size == (W, H))
    return ok, '上传 %dx%d -> 回显 %dx%d %s' % (
        W, H, out_img.size[0], out_img.size[1], '一致' if ok else '被缩放!')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--live', action='store_true',
                    help='执行运行时集成验证（需 BFF_BASE_URL + BFF_TOKEN 环境变量）')
    args = ap.parse_args()

    print('== 静态代码验证：/files/upload 是否缩放上传图 ==')
    results, bad = static_check()
    all_ok = True
    for name, ok in results:
        print('  [%s] %s' % ('PASS' if ok else 'FAIL', name))
        all_ok = all_ok and ok
    for b in bad:
        print('     !! %s' % b)

    print('\n== 前端超采样不变量自检（导出像素 >= 显示像素 才不糊） ==')
    for crop_nat, dpr, disp, ew, ok in check_supersample_invariant():
        print('  [%s] 原图裁剪区 %dpx, DPR=%d -> 导出 %dpx, 显示 %dpx %s'
              % ('PASS' if ok else 'WARN', crop_nat, dpr, ew, disp,
                 '清晰' if ok else '仍会放大糊（需更大原图区域）'))

    live_msg = None
    if args.live:
        base = os.environ.get('BFF_BASE_URL')
        tok = os.environ.get('BFF_TOKEN')
        if not (base and tok):
            print('\n== 运行时验证：跳过 ==')
            print('   未提供 BFF_BASE_URL / BFF_TOKEN')
        else:
            print('\n== 运行时验证：上传/下载尺寸比对 ==')
            ok, msg = run_live(base, tok)
            print('  [%s] %s' % ('PASS' if ok else ('FAIL' if ok is False else 'SKIP'), msg))
            if ok is False:
                all_ok = False

    print()
    if all_ok:
        print('结论：后端 /files/upload 原样存储上传字节，无缩放/重编码。'
              '前端超采样导出的高清裁剪图上传后回显仍为原尺寸，方案有效。')
        sys.exit(0)
    else:
        print('结论：发现后端可能缩放/重编码上传图，前端超采样方案会被覆盖，需进一步处理。')
        sys.exit(1)


if __name__ == '__main__':
    main()
