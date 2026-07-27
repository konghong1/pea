"""后端 param_adapters 转换路径测试：上传真实图片到 MinIO，再用内部签名 URL 走 _normalize_refs，
验证其被转成 data:image/...;base64,（完整修复路径）。
在容器内运行：
  cd verify && docker cp test_param_adapters2.py pea-server-generation-orchestrator-1:/app/t.py
  docker exec pea-server-generation-orchestrator-1 python t.py
"""
import sys, os, base64, io
sys.path.insert(0, '/app')
ok = 0; fail = 0
def check(n, c, e=""):
    global ok, fail
    if c: ok += 1; print(f"  PASS  {n} {e}")
    else: fail += 1; print(f"  FAIL  {n} {e}")

from app.param_adapters import _is_internal_url, _normalize_refs, _resolve_internal_ref_via_minio
from app.storage import _get_client

# 构造一张 1x1 PNG
import struct, zlib
def make_png():
    w=h=1
    raw = b'\x00\xff\x00\x80'  # RGBA
    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw)
    return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
png = make_png()
key = "verify_tests/real1x1.png"
client = _get_client()
client.put_object('pea-media', key, io.BytesIO(png), length=len(png))
print(f"  uploaded key={key} ({len(png)} bytes)")

# 用与 BFF 签名 URL 相同形态的内部 URL（localhost:9000 + /pea-media/ 前缀）
fake_signed = f"http://localhost:9000/pea-media/{key}?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600"
check("is_internal true for our url", _is_internal_url(fake_signed) is True)
data_uri = _resolve_internal_ref_via_minio(fake_signed)
check("resolve returns data: uri", bool(data_uri) and data_uri.startswith("data:image/png;base64,"),
      (data_uri[:40] if data_uri else "None"))
if data_uri:
    b64 = data_uri.split(",", 1)[1]
    check("data: uri decodes back to original png", base64.b64decode(b64) == png)

# _normalize_refs 端到端：内部 URL 应被转成 data: uri
norm = _normalize_refs([fake_signed])
check("normalize converts internal->data:", len(norm) == 1 and norm[0].startswith("data:image/png;base64,"),
      norm[0][:40] if norm else "empty")

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
