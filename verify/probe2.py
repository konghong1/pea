import sys, time
sys.path.insert(0, "/app")
print("A", flush=True)
from app import storage
print("B", flush=True)
c = storage._get_client()
print("C client-ok", flush=True)
t = time.time()
try:
    exists = c.bucket_exists("pea-media")
    print("D bucket_exists=", exists, "took=%.1fs" % (time.time() - t), flush=True)
except Exception as e:
    print("D bucket_exists FAILED:", repr(e), "took=%.1fs" % (time.time() - t), flush=True)
t = time.time()
try:
    import io
    c.put_object("pea-media", "probe/hello.txt", io.BytesIO(b"hi"), length=2, content_type="text/plain")
    print("E put_object OK took=%.1fs" % (time.time() - t), flush=True)
except Exception as e:
    print("E put_object FAILED:", repr(e), "took=%.1fs" % (time.time() - t), flush=True)
