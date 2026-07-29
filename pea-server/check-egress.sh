#!/usr/bin/env bash
#
# pea Creative OS — 服务器出网自检 (部署前必跑)
# 用法: 在服务器的 pea-server/ 目录下执行  bash check-egress.sh
#
# 判定"本机能否访问 AI 提供商 (apihub.agnes-ai.com)", 并直接给出 .env 配置建议:
#   ① 直连成功           -> PEA_PROXY_FIX=0 (默认), 无需任何额外配置
#   ② DNS 被污染但 IP 直连成功 -> PEA_PROXY_FIX=0 + PEA_DNS_FIX=1 (默认已开)
#   ③ 直连被阻断(TLS/超时)     -> 必须在本机跑一个出网代理, 然后 PEA_PROXY_FIX=1
#
set -u

DOMAIN="apihub.agnes-ai.com"
# 经 DoH (dns.google / cloudflare-dns.com) 双源验证的真实 Cloudflare IP (2026-07-29)。
# 若失效: curl -s "https://dns.google/resolve?name=apihub.agnes-ai.com&type=A" 重新获取。
REAL_IPS=("104.18.18.62" "104.18.19.62")
PROXY_PORT="${PEA_EGRESS_PROXY_PORT:-33210}"

G="\033[1;32m"; Y="\033[1;33m"; R="\033[1;31m"; B="\033[1;34m"; N="\033[0m"
ok()   { echo -e "${G}[✓]${N} $*"; }
warn() { echo -e "${Y}[!]${N} $*"; }
bad()  { echo -e "${R}[✗]${N} $*"; }
info() { echo -e "${B}[i]${N} $*"; }

echo "==== pea 出网自检: ${DOMAIN} ===="

# ---- 1. 本机 DNS 解析是否被污染 ----
info "1/4 检查本机 DNS 解析..."
RESOLVED=$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u | head -5)
if [ -z "$RESOLVED" ]; then
  RESOLVED=$(nslookup "$DOMAIN" 2>/dev/null | awk '/^Address: /{print $2}' | grep -v ':' | head -5)
fi
DNS_POLLUTED=1
for ip in $RESOLVED; do
  for real in "${REAL_IPS[@]}"; do
    [ "$ip" = "$real" ] && DNS_POLLUTED=0
  done
  # Cloudflare 常用网段 104.16-31.x / 172.64-71.x 也视为可信
  case "$ip" in
    104.1[6-9].*|104.2[0-9].*|104.3[0-1].*|172.6[4-9].*|172.7[0-1].*) DNS_POLLUTED=0 ;;
  esac
done
if [ -z "$RESOLVED" ]; then
  bad "本机无法解析 ${DOMAIN}"
elif [ "$DNS_POLLUTED" = "1" ]; then
  warn "本机 DNS 解析疑似被污染: 解析结果 [$(echo $RESOLVED | tr '\n' ' ')], 与真实 Cloudflare IP 不符"
else
  ok "本机 DNS 解析正常: $(echo $RESOLVED | tr '\n' ' ')"
fi

# ---- 2. 直连测试 (走本机 DNS) ----
info "2/4 直连测试 (本机 DNS)..."
CODE=$(curl -s --noproxy '*' -m 12 -o /dev/null -w '%{http_code}' "https://${DOMAIN}/v1/models" 2>/dev/null)
DIRECT_OK=0
if [ "$CODE" != "000" ] && [ -n "$CODE" ]; then
  ok "直连成功 (HTTP ${CODE}; 401 也算通, 说明 TLS 已握手到真实服务)"
  DIRECT_OK=1
else
  warn "直连失败 (超时或 TLS 被重置)"
fi

# ---- 3. 用真实 IP 绕过 DNS 再测 (判定是否仅 DNS 问题) ----
IP_OK=0
if [ "$DIRECT_OK" = "0" ]; then
  info "3/4 用真实 IP 绕过 DNS 直连测试..."
  for ip in "${REAL_IPS[@]}"; do
    CODE=$(curl -s --noproxy '*' -m 12 --resolve "${DOMAIN}:443:${ip}" -o /dev/null -w '%{http_code}' "https://${DOMAIN}/v1/models" 2>/dev/null)
    if [ "$CODE" != "000" ] && [ -n "$CODE" ]; then
      ok "经真实 IP ${ip} 直连成功 (HTTP ${CODE}) —— 仅 DNS 被污染, 连接本身未被阻断"
      IP_OK=1; break
    else
      warn "经真实 IP ${ip} 仍失败 (TLS/网络层被阻断)"
    fi
  done
else
  info "3/4 跳过 (直连已成功)"
  IP_OK=1
fi

# ---- 4. 本机代理端口检测 ----
info "4/4 检查本机出网代理 (127.0.0.1:${PROXY_PORT})..."
PROXY_UP=0
if (exec 3<>"/dev/tcp/127.0.0.1/${PROXY_PORT}") 2>/dev/null; then
  exec 3>&- 3<&-
  PROXY_UP=1
  CODE=$(curl -s -m 15 -x "http://127.0.0.1:${PROXY_PORT}" -o /dev/null -w '%{http_code}' "https://${DOMAIN}/v1/models" 2>/dev/null)
  if [ "$CODE" != "000" ] && [ -n "$CODE" ]; then
    ok "本机代理可用且能访问 ${DOMAIN} (HTTP ${CODE})"
  else
    warn "本机 ${PROXY_PORT} 端口有监听, 但经它访问 ${DOMAIN} 失败"
    PROXY_UP=0
  fi
else
  warn "本机 ${PROXY_PORT} 端口无代理监听"
fi

# ---- 结论 ----
echo
echo "==== 结论与 .env 建议 ===="
if [ "$DIRECT_OK" = "1" ]; then
  ok "本服务器可直连 AI 提供商。.env 保持: PEA_PROXY_FIX=0 (PEA_DNS_FIX 开关均可)"
elif [ "$IP_OK" = "1" ]; then
  ok "仅 DNS 被污染, IP 直连可用。.env 保持: PEA_PROXY_FIX=0, PEA_DNS_FIX=1 (默认已开, dns-override 会写死真实 IP)"
elif [ "$PROXY_UP" = "1" ]; then
  ok "直连被阻断, 但本机代理可用。.env 设: PEA_PROXY_FIX=1 (可用 PEA_EGRESS_PROXY 指定其它端口)"
else
  bad "直连被阻断且本机无可用代理 —— 容器内一定也访问不到 AI 提供商!"
  echo "   解决(二选一):"
  echo "   a) 在本服务器部署一个能出境的 HTTP 代理(监听 127.0.0.1:${PROXY_PORT} 或任意端口),"
  echo "      然后 .env 设 PEA_PROXY_FIX=1 (+ PEA_EGRESS_PROXY=http://host.docker.internal:<端口>)"
  echo "   b) 换用境内可直连的 AI 提供商中转地址(管理后台把 provider 的 base_url 换成中转地址)"
  exit 2
fi
exit 0
