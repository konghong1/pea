import sys, time
sys.path.insert(0, "/app")
from app import storage
c = storage._get_client()
policy = storage._public_policy("pea-media", storage.settings.media_public_prefix)
print("calling set_bucket_policy", flush=True)
t = time.time()
try:
    c.set_bucket_policy("pea-media", policy)
    print("set_bucket_policy OK took=%.1fs" % (time.time() - t), flush=True)
except Exception as e:
    print("set_bucket_policy FAILED:", repr(e), "took=%.1fs" % (time.time() - t), flush=True)
# also read current policy
try:
    cur = c.get_bucket_policy("pea-media")
    print("CURRENT POLICY present:", bool(cur), flush=True)
except Exception as e:
    print("get_bucket_policy err:", repr(e), flush=True)
