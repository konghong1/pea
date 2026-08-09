#!/usr/bin/env python3
"""
管理端可视化定价 —— 真实环境 E2E (对运行中的 BFF :4100)。

验证「手写 JSON 改成可视化表单」整条后端链路在真实环境可用:
  1. 管理员登录拿 JWT
  2. preview-cost: 草稿态试算, 价格由服务端权威计算 (与真实扣费同源)
  3. 建模型: 同时落库 pricing_json + params_schema_json (两份 JSON 一次保存)
  4. 读回: 确认两份 JSON 都正确持久化 (维度不再漂移)
  5. DTO 校验: 非法定价在落库前被服务端拦下 (400)
  6. 清理: 删除测试模型

用法: python verify/verify_admin_pricing_e2e.py   (BFF 需在 4100 跑着且已含本功能)
退出码: 任一断言失败 → 1
"""
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:4100/api"
EMAIL = "admin@pea.ai"
PASSWORD = "admin12345"

fails = 0


def req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode() or "null")
        except Exception:
            payload = None
        return e.code, payload


def check(cond, msg, extra=""):
    global fails
    if cond:
        print("  PASS ", msg)
    else:
        print("  FAIL ", msg, ("  " + extra) if extra else "")
        fails += 1


print("— 1. 管理员登录 —")
status, body = req("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
check(status in (200, 201), "登录成功", f"status={status} body={body}")
token = (body or {}).get("token") if isinstance(body, dict) else None
check(bool(token), "拿到 admin JWT")

print("— 2. preview-cost: 草稿试算 (服务端权威计价) —")
pricing = {
    "base": 10,
    "tiers": {"size": {"1K": 0, "2K": 5, "4K": 20}, "quality": {"standard": 0, "high": 8}},
    "multiplier": "n",
}
params = {"size": "4K", "quality": "high", "n": 2}
status, body = req("POST", "/admin/models/preview-cost", token, {"pricing": pricing, "params": params})
check(status in (200, 201), "preview-cost 调通", f"status={status} body={body}")
cost = (body or {}).get("cost")
# (base 10 + 4K 20 + high 8) * min(n=2, 8) = 38 * 2 = 76
check(cost == 76, "试算价 = 76 (10+20+8)*2", f"cost={cost}")
# 明细里应能看到每个维度的加价拆项
items = (body or {}).get("items") or []
check(any(it.get("dim") == "size" and it.get("value") == "4K" for it in items), "明细含 size=4K 档")

print("— 3. 建模型: 一次保存 pricing + paramsSchema —")
# 复用任一现存的 providerId (避免 FK 问题)
status, lst = req("GET", "/admin/models", token)
provider_id = None
if isinstance(lst, list) and lst:
    provider_id = lst[0].get("providerId")
check(bool(provider_id), "取得 providerId", f"providerId={provider_id}")
model_id = "e2e_pricing_%d" % int(time.time())
params_schema = {"size": ["1K", "2K", "4K"], "quality": ["standard", "high"], "n": [1, 2, 4]}
create_payload = {
    "id": model_id,
    "providerId": provider_id,
    "modelName": "e2e-pricing-test",
    "modelType": "image",
    "displayName": "E2E 定价测试",
    "pricing": pricing,
    "paramsSchema": params_schema,
}
status, body = req("POST", "/admin/models", token, create_payload)
check(status in (200, 201), "模型创建成功", f"status={status} body={body}")

print("— 4. 读回: 两份 JSON 都正确持久化 —")
status, lst = req("GET", "/admin/models", token)
check(status in (200, 201), "模型列表可读", f"status={status}")
created = next((m for m in (lst or []) if m.get("id") == model_id), None)
check(created is not None, "测试模型在列表中", f"model_id={model_id}")
if created:
    saved_pricing = created.get("pricing") or {}
    saved_schema = created.get("paramsSchema") or {}
    check(saved_pricing.get("base") == 10, "基础价持久化", f"base={saved_pricing.get('base')}")
    check(saved_pricing.get("tiers", {}).get("size", {}).get("4K") == 20, "size=4K 加价持久化")
    check(saved_pricing.get("multiplier") == "n", "数量倍率参数名持久化")
    check(saved_schema.get("size") == ["1K", "2K", "4K"], "paramsSchema.size 持久化", f"{saved_schema.get('size')}")
    check(saved_schema.get("n") == [1, 2, 4], "paramsSchema.n 持久化 (数字数组)", f"{saved_schema.get('n')}")

print("— 5. DTO 校验: 非法定价被服务端拦下 —")
bad_pricing = {"base": -5, "tiers": "oops"}  # base 为负 + tiers 非对象
status, body = req("POST", "/admin/models/preview-cost", token, {"pricing": bad_pricing, "params": {}})
check(status == 400, "非法定价被 400 拒绝", f"status={status} body={body}")

print("— 6. 清理: 删除测试模型 —")
if created:
    status, body = req("DELETE", "/admin/models/" + model_id, token)
    check(status in (200, 204), "测试模型已删除", f"status={status}")

print("")
if fails:
    print("❌ %d 条 E2E 断言失败" % fails)
    sys.exit(1)
print("✅ 管理端定价 E2E 全部通过")
