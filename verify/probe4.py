import sys, time
sys.path.insert(0, "/app")
from app import storage
data = b"x" * 100
print("calling store_bytes", flush=True)
t = time.time()
try:
    url = storage.store_bytes(data, "video", user_id=1, content_type="video/mp4")
    print("store_bytes OK url=", url, "took=%.1fs" % (time.time() - t), flush=True)
except Exception as e:
    print("store_bytes FAILED:", repr(e), "took=%.1fs" % (time.time() - t), flush=True)
