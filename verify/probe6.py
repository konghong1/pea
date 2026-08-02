import sys, time, io
sys.path.insert(0, "/app")
from app import storage
data = b"x" * 100
print("1 _ensure_bucket", flush=True)
storage._ensure_bucket()
print("2 ensure_public_policy_once", flush=True)
storage.ensure_public_policy_once()
print("3 build key", flush=True)
key = storage._build_key("video", 1, ".mp4")
print("4 put_object", flush=True)
t = time.time()
storage._get_client().put_object("pea-media", key, io.BytesIO(data), length=len(data), content_type="video/mp4")
print("5 put done %.1fs" % (time.time() - t), flush=True)
print("6 build url", flush=True)
url = f"{storage.settings.cdn_base_url}/{key}"
print("URL=", url, flush=True)
