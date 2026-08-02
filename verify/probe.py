print("T1", flush=True)
import sys
sys.path.insert(0, "/app")
print("T2", flush=True)
import json
print("T3", flush=True)
from app import db
print("T4 db", flush=True)
from app import storage
print("T5 storage", flush=True)
from app.async_core.dispatcher import finalize_job
print("T6 dispatcher", flush=True)
from app.async_core.engine import ensure_started
print("T7 engine", flush=True)
ensure_started()
print("T8 ensure_started OK", flush=True)
