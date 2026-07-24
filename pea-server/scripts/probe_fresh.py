import json, uuid, urllib.request, urllib.error, urllib.parse

BASE = "http://localhost:4100"

def _req(method, path, *, token=None, body=None, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"content-type": "application/json", "accept": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            payload = resp.read().decode() or "{}"
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads((e.read() or b"{}").decode() or "{}")

suffix = uuid.uuid4().hex[:8]
email = f"probe_{suffix}@pea.ai"
st, reg = _req("POST", "/auth/register", body={"email": email, "password": "password123", "displayName": "probe"})
print("register:", st, reg)
token = reg.get("token")
if not token:
    print("NO TOKEN", reg); raise SystemExit(1)

st, lst = _req("GET", "/canvases", token=token)
print("list status:", st)
print("count(before create):", len(lst) if isinstance(lst, list) else lst)

# create one
st, created = _req("POST", "/canvases", token=token, body={"title": "测试画布A", "scope": "personal"})
print("create status:", st, created)
st, lst = _req("GET", "/canvases", token=token)
print("count(after 1 create):", len(lst) if isinstance(lst, list) else lst)
for c in (lst if isinstance(lst, list) else []):
    print("  id=%s title=%r scope=%s owner=%s" % (c.get("id"), c.get("title"), c.get("scope"), c.get("owner_id")))
