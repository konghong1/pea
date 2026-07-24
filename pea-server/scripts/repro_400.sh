#!/usr/bin/env bash
# 复现验证：GET /canvases 曾返回 400。修复后应当 200 且返回数组。
set -e
BFF=http://localhost:4100
EMAIL="verify_$(date +%s)@pea.ai"
PASS="password123"

echo "== register =="
REG=$(curl -s -X POST "$BFF/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\",\"displayName\":\"verify\"}")
echo "$REG"
TOKEN=$(echo "$REG" | python -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
if [ -z "$TOKEN" ]; then echo "NO TOKEN"; exit 1; fi

echo "== GET /canvases?scope=personal&limit=100 =="
curl -s -o /tmp/resp.json -w "HTTP %{http_code}\n" \
  "$BFF/canvases?scope=personal&limit=100" \
  -H "Authorization: Bearer $TOKEN"
echo "--- body ---"
cat /tmp/resp.json
echo
echo "== GET /canvases (no params) =="
curl -s -o /tmp/resp2.json -w "HTTP %{http_code}\n" \
  "$BFF/canvases" \
  -H "Authorization: Bearer $TOKEN"
cat /tmp/resp2.json
echo
