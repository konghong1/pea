#!/usr/bin/env bash
#
# pea Creative OS — 服务器出网自检 (部署前必跑)
# 用法: 在服务器的 pea-server/ 目录下执行  bash check-egress.sh
#
# 判定"本机(及容器内)能否访问 AI 提供商 (apihub.agnes-ai.com)", 并直接给出 .env 配置建议:
#   ① 直连成功                -> PEA_PROXY_FIX=0 (默认), 无需任何额外配置
#   ② DNS 被污染但 IP 直连成功 -> PEA_PROXY_FIX=0 + PEA_DNS_FIX=1 (默认已开)
#   ③ 直连被阻断 + 本机有可用代理(且容器可达) -> PEA_PROXY_FIX=1
#   ④ 代理只监听回环(容器访问不到) -> 改代理监听 0.0.0.0 / docker 网桥
#
# 注意: PEA_EGRESS_PROXY 默认 host.docker.internal:33210 是“开发沙箱专属”地址,
#       仅当你的开发机跑了 WorkBuddy 沙箱代理时才有意义。搬到生产服务器前请确认
#       该服务器上确有可出网的代理监听在对应地址, 否则此处会直接判失败。
set -u

DOMAIN="apihub.agnes-ai.com"
# 经 DoH (dns.google / cloudflare-dns.com) 双源验证的真实 Cloudflare IP (2026-07-29)。
# 若失效: curl -s "https://dns.google/resolve?name=apihub.agnes-ai.com&type=A" 重新获取。
REAL_IPS=("104.18.18.62" "104.18.19.62")

G="\033[1;32m"; Y="\033[1;33m"; R="\033[1;31m"; B="\033[1;34m"; N="\033[0m"
ok()   { echo -e "${G}[✓]${N} $*"; }
warn() { echo -e "${Y}[!]${N} $*"; }
bad()  { echo -e "${R}[✗]${N} $*"; }
info() { echo -e "${B}[i]${N} $*"; }

# ---- 读取 .env 中实际代理配置 (优先 PEA_EGRESS_PROXY, 否则默认 127.0.0.1:33210) ----
PROXY_URL="${PEA_EGRESS_PROXY:-}"
if [ -z "$PROXY_URL" ] && [ -f .env ]; then
  PROXY_URL=$(grep -E '^PEA_EGRESS_PROXY=' .env | tail -1 | cut -d= -f2-)
fi
if [ -n "$PROXY_URL" ]; then
  p=${PROXY_URL#*://}
  PROXY_HOST=${p%%:*}
  PROXY_PORT=${p##*:}
  PROXY_PORT=${PROXY_PORT%%/*}
else
  PROXY_HOST="127.0.0.1"
  PROXY_PORT="33210"
fi
# 容器经 host.docker.internal 访问宿主, 在 Linux 上通常映射到 docker 网桥网关 IP
BRIDGE_IP=$( (docker network inspect bridge -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null) | head -1 )
[ -z "$BRIDGE_IP" ] && BRIDGE_IP="172.17.0.1"

echo "==== pea 出网自检: ${DOMAIN} ===="
info "检测用代理地址: ${PROXY_HOST}:${PROXY_PORT} (来自 PEA_EGRESS_PROXY 或默认)"
info "docker 网桥 IP (容器视角的宿主): ${BRIDGE_IP}"

# ---- 1. 本机 DNS 解析是否被污染 ----
info "1/5 检查本机 DNS 解析..."
RESOLVED=$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk '{print $1}' | sort -u | head -5)
if [ -z "$RESOLVED" ]; then
  RESOLVED=$(nslookup "$DOMAIN" 2>/dev/null | awk '/^Address: /{print $2}' | grep -v ':' | head -5)
fi
DNS_POLLUTED=1
for ip in $RESOLVED; do
  for real in "${REAL_IPS[@]}"; do
    [ "$ip" = "$real" ] && DNS_POLLUTED=0
  done
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
info "2/5 直连测试 (本机 DNS)..."
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
  info "3/5 用真实 IP 绕过 DNS 直连测试..."
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
  info "3/5 跳过 (直连已成功)"
  IP_OK=1
fi

# ---- 4. 本机代理端口检测 (宿主视角) ----
info "4/5 检查本机出网代理 (${PROXY_HOST}:${PROXY_PORT})..."
PROXY_UP=0
if (exec 3<>"/dev/tcp/${PROXY_HOST}/${PROXY_PORT}") 2>/dev/null; then
  exec 3>&- 3<&-
  CODE=$(curl -s -m 15 -x "http://${PROXY_HOST}:${PROXY_PORT}" -o /dev/null -w '%{http_code}' "https://${DOMAIN}/v1/models" 2>/dev/null)
  if [ "$CODE" != "000" ] && [ -n "$CODE" ]; then
    ok "本机代理可用且能访问 ${DOMAIN} (HTTP ${CODE})"
    PROXY_UP=1
  else
    warn "本机 ${PROXY_HOST}:${PROXY_PORT} 端口有监听, 但经它访问 ${DOMAIN} 失败"
  fi
else
  warn "本机 ${PROXY_HOST}:${PROXY_PORT} 无代理监听"
fi

# ---- 5. 容器视角: 代理是否监听在非回环地址 (容器经 host.docker.internal 访问) ----
info "5/5 检查代理是否可从容器访问 (host.docker.internal -> ${BRIDGE_IP})..."
LOOPBACK_ONLY=0
# 若配置的是回环地址(127.0.0.1/localhost/host.docker.internal 本质是宿主回环的别名),
# 容器经网桥 IP 访问时, 仅监听回环的代理会拒绝连接。
if [ "$PROXY_HOST" = "127.0.0.1" ] || [ "$PROXY_HOST" = "localhost" ] || [ "$PROXY_HOST" = "host.docker.internal" ]; then
  if (exec 3<>"/dev/tcp/${BRIDGE_IP}/${PROXY_PORT}") 2>/dev/null; then
    exec 3>&- 3<&-
    info "代理可从容器视角(${BRIDGE_IP}:${PROXY_PORT})访问"
  else
    LOOPBACK_ONLY=1
    bad "代理只监听回环(${PROXY_HOST}), 容器经 host.docker.internal(${BRIDGE_IP})访问不到!"
    bad "修复: 让代理监听 0.0.0.0 或 ${BRIDGE_IP} (如 clash: 开启 allow-lan 并绑定 0.0.0.0)。"
  fi
fi

# ---- 结论 ----
echo
echo "==== 结论与 .env 建议 ===="
if [ "$DIRECT_OK" = "1" ]; then
  ok "本服务器可直连 AI 提供商。.env 保持: PEA_PROXY_FIX=0 (PEA_DNS_FIX 开关均可)"
elif [ "$IP_OK" = "1" ]; then
  ok "仅 DNS 被污染, IP 直连可用。.env 保持: PEA_PROXY_FIX=0, PEA_DNS_FIX=1 (默认已开)"
elif [ "$PROXY_UP" = "1" ] && [ "$LOOPBACK_ONLY" = "0" ]; then
  ok "直连被阻断, 但本机代理可用且容器可访问。"
  ok ".env 设: PEA_PROXY_FIX=1  PEA_EGRESS_PROXY=http://host.docker.internal:${PROXY_PORT}"
elif [ "$PROXY_UP" = "1" ] && [ "$LOOPBACK_ONLY" = "1" ]; then
  bad "代理可用, 但只监听回环, 容器访问不到! 先按上面 5/5 修复代理绑定, 再设 PEA_PROXY_FIX=1。"
  exit 2
else
  bad "直连被阻断且本机无可用代理 —— 容器内一定也访问不到 AI 提供商!"
  echo "   解决(二选一):"
  echo "   a) 在本服务器部署一个能出境的 HTTP 代理(监听 0.0.0.0:${PROXY_PORT}), 然后 .env 设 PEA_PROXY_FIX=1"
  echo "   b) 换用境内可直连的 AI 提供商中转地址(管理后台把 provider 的 base_url 换成中转地址), PEA_PROXY_FIX=0"
  exit 2
fi
exit 0
