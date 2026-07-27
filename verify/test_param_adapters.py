"""后端 param_adapters 单元测试：验证内部 MinIO URL 检测与 data: URI 转换。
在编排器容器内运行：
  docker cp verify/test_param_adapters.py pea-server-generation-orchestrator-1:/app/test_param_adapters.py
  docker exec pea-server-generation-orchestrator-1 python test_param_adapters.py
"""
import sys, os
sys.path.insert(0, '/app')

ok = 0
fail = 0

def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")

from app.param_adapters import _is_internal_url, _normalize_refs

# 1) 检测：BFF 签名 URL（localhost:9000）→ 内部
check("detect localhost:9000",
      _is_internal_url("http://localhost:9000/pea-media/u:1/abc.png?X-Amz-abc") is True)

# 2) 检测：公网图（picsum）→ 外部
check("allow picsum",
      _is_internal_url("https://picsum.photos/seed/x/200/200") is False)

# 3) 检测：data: URI → 外部（无需转换）
check("allow data: uri",
      _is_internal_url("data:image/png;base64,AAA") is False)

# 4) 检测：minio 容器名 → 内部
check("detect minio host",
      _is_internal_url("http://minio:9000/pea-media/k") is True)

# 5) _normalize_refs 保留顺序 + 外部图直通
refs = [
    "https://picsum.photos/seed/a/200/200",
    "http://localhost:9000/pea-media/u:1/x.png?sig=1",
    "https://picsum.photos/seed/b/200/200",
]
norm = _normalize_refs(refs)
check("normalize keeps order (len=3)", len(norm) == 3, f"got {len(norm)}")
check("normalize external pass-through first", norm[0].startswith("https://picsum.photos/seed/a"), norm[0][:40])
check("normalize external pass-through last", norm[-1].startswith("https://picsum.photos/seed/b"), norm[-1][:40])
# 中间的 localhost URL 要么转成 data: 要么（对象不存在）被丢弃；都不能原样保留 localhost
mid = norm[1]
check("internal url not forwarded as-is", not mid.startswith("http://localhost:9000"),
      f"mid={mid[:60]}")

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
