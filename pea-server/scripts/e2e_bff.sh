#!/usr/bin/env bash
# pea BFF 真实链路 e2e (Tier-3 验证). 前置: BFF(:4000) + Orchestrator(:8000) + MySQL + Redis 已起.
set -u
BFF=http://localhost:4000
pass=0; fail=0
ok(){ echo "  [PASS] $1"; pass=$((pass+1)); }
bad(){ echo "  [FAIL] $1 :: $2"; fail=$((fail+1)); }
json(){ python -c "import sys,json;print(json.load(sys.stdin) $1)" 2>/dev/null; }

echo "== 1. 注册 -> 账户自动创建(赠 free Tapies) =="
REG=$(curl -s -X POST $BFF/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"qa_'"$RANDOM"'@pea.dev","password":"pw123456","displayName":"QA"}')
TOKEN=$(echo "$REG" | json "| '$access_token' if 'access_token' in d else d.get('token','')")
echo "$REG" | grep -q access_token && ok "register 返回 token" || bad "register" "$REG"
USERID=$(echo "$REG" | json "| str(d.get('user',{}).get('id',''))")

echo "== 2. 初始余额 = 1000 =="
BAL=$(curl -s $BFF/billing/balance -H "Authorization: Bearer $TOKEN")
B0=$(echo "$BAL" | json "| d['balance']")
[ "$B0" = "1000" ] && ok "初始余额=1000 (got $B0)" || bad "初始余额" "$BAL"

echo "== 3. 提交生成 -> 预扣 10 -> 余额 990 =="
ACC=$(curl -s -X POST $BFF/generation/jobs -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"type":"image","prompt":"a premium product shot","costTapies":10}')
JOB=$(echo "$ACC" | json "| d.get('jobId','')")
echo "$ACC" | grep -q jobId && ok "generation accept 返回 jobId ($JOB)" || bad "generation accept" "$ACC"
sleep 1
BAL2=$(curl -s $BFF/billing/balance -H "Authorization: Bearer $TOKEN")
B1=$(echo "$BAL2" | json "| d['balance']")
[ "$B1" = "990" ] && ok "预扣后余额=990 (got $B1)" || bad "预扣后余额" "$BAL2"

echo "== 4. worker 已消费(编排器进程内) -> job 终态 =="
sleep 1
JST=$(curl -s "$BFF/generation/jobs/$JOB" -H "Authorization: Bearer $TOKEN")
STATUS=$(echo "$JST" | json "| d.get('status','')")
echo "job status=$STATUS"
[ "$STATUS" = "done" ] && ok "job 跑到 done (mock 出图)" || bad "job 状态" "$JST"

echo "== 5. 内部退款幂等(模拟 orchestrator 补偿) =="
REF1=$(curl -s -X POST $BFF/internal/billing/refund -H "X-Service-Token: dev-token" -H 'Content-Type: application/json' \
  -d "{\"userId\":$USERID,\"amount\":10,\"txnId\":\"e2e-refund-1\",\"jobId\":\"$JOB\"}")
echo "$REF1" | grep -q '"ok":true' && ok "refund 第一次成功" || bad "refund#1" "$REF1"
BAL3=$(curl -s $BFF/billing/balance -H "Authorization: Bearer $TOKEN")
B2=$(echo "$BAL3" | json "| d['balance']")
[ "$B2" = "1000" ] && ok "退款后余额回 1000 (got $B2)" || bad "退款后余额" "$BAL3"
REF2=$(curl -s -X POST $BFF/internal/billing/refund -H "X-Service-Token: dev-token" -H 'Content-Type: application/json' \
  -d "{\"userId\":$USERID,\"amount\":10,\"txnId\":\"e2e-refund-1\",\"jobId\":\"$JOB\"}")
BAL4=$(curl -s $BFF/billing/balance -H "Authorization: Bearer $TOKEN")
B3=$(echo "$BAL4" | json "| d['balance']")
[ "$B3" = "1000" ] && ok "重复退款幂等: 余额仍 1000 (未双退)" || bad "退款幂等" "$BAL4"

echo "== 6. 双记账本可追溯 =="
LED=$(curl -s $BFF/billing/ledger -H "Authorization: Bearer $TOKEN")
ENTRIES=$(echo "$LED" | json "| len(d)")
echo "ledger 行数=$ENTRIES"
echo "$LED" | grep -q preauth && ok "ledger 含 preauth 分录" || bad "ledger preauth" "$LED"
echo "$LED" | grep -q refund && ok "ledger 含 refund 分录" || bad "ledger refund" "$LED"

echo ""
echo "=== e2e 结果: PASS=$pass FAIL=$fail ==="
[ "$fail" = "0" ] && exit 0 || exit 1
