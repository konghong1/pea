import json, time, urllib.request, urllib.error

BFF = "http://localhost:4100"
WEB = "http://localhost:8088"  # nginx, proxies /media -> minio

def req(method, url, token=None, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# 1) login as admin
st, txt = req("POST", f"{BFF}/auth/login", body={"email":"admin@pea.ai","password":"admin12345"})
print("LOGIN", st, txt[:200])
tok = json.loads(txt)["token"]

def poll(job_id, label, max_wait=300):
    print(f"\n=== {label} job={job_id} ===")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        st, txt = req("GET", f"{BFF}/generation/jobs/{job_id}", token=tok)
        try:
            d = json.loads(txt)
        except Exception:
            print("  parse err", st, txt[:150]); time.sleep(3); continue
        status = d.get("status")
        print(f"  t={int(time.time())%100000} status={status} keys={list(d.keys())}")
        if status in ("succeeded","success","completed"):
            res = d.get("result") or {}
            url = res.get("url") or (res.get("urls") or [None])[0] if isinstance(res.get("urls"),list) else None
            print("  RESULT:", json.dumps(res, ensure_ascii=False)[:400])
            if url:
                # check accessibility via nginx /media
                if url.startswith("/"):
                    u = WEB + url
                else:
                    u = url
                cst, _ = req("GET", u, timeout=20)
                print(f"  FETCH {u} -> {cst}")
            return d
        if status in ("failed","error"):
            print("  FAILED err=", d.get("error"))
            return d
        time.sleep(3)
    print("  TIMEOUT (still polling)")
    return d

# 2) IMAGE
st, txt = req("POST", f"{BFF}/generation/node", token=tok,
              body={"type":"image","model":"agnes-image-2.0-flash",
                    "prompt":"a cute cat on a sofa, studio light","params":{"size":"1K","n":1}})
print("\nIMAGE SUBMIT", st, txt[:300])
if st == 201:
    jid = json.loads(txt)["jobId"]
    poll(jid, "IMAGE", max_wait=300)

# 3) VIDEO
st, txt = req("POST", f"{BFF}/generation/node", token=tok,
              body={"type":"video","model":"agnes-video-v2.0",
                    "prompt":"a cat walking on a beach, cinematic","params":{"duration":5,"n":1}})
print("\nVIDEO SUBMIT", st, txt[:300])
if st == 201:
    jid = json.loads(txt)["jobId"]
    poll(jid, "VIDEO", max_wait=540)
print("\nDONE")
