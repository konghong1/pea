import json, urllib.request

req = urllib.request.Request(
    "http://localhost:8088/auth/register",
    data=json.dumps({"email": "testdbg2@pea.ai", "password": "Password123"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print("OK:", resp.status, resp.read().decode())
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code, e.read().decode())