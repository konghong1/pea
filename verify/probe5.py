import sys, time
sys.path.insert(0, "/app")
from app import storage
client = storage._get_client()
policy = storage._public_policy("pea-media", storage.settings.media_public_prefix)
print("apply_policy_now", flush=True)
t = time.time()
ok = storage._apply_policy_now(client, "pea-media", policy)
print("apply_policy_now ->", ok, "took=%.1fs" % (time.time() - t), flush=True)
print("ensure_public_policy_once", flush=True)
t = time.time()
storage.ensure_public_policy_once()
print("ensure_public_policy_once done took=%.1fs" % (time.time() - t), flush=True)
