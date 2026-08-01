import { useEffect, useRef } from 'react';
import { useAuth } from '../store/auth';

/**
 * 连接 BFF WebSocket (/ws), 鉴权后接收实时事件:
 *  - balance.changed -> 更新顶栏余额
 *  - job.updated / notification -> 派发 window CustomEvent 供组件订阅
 *
 * 可靠性设计（修复「生成后余额不刷新，要手动点一下」）：
 *  1. 断线自动重连（指数退避 1s→30s + 抖动），此前 onclose 无处理，一旦掉线便永久失联；
 *  2. 每次连接成功后补拉一次余额 —— 断连窗口内错过的 balance.changed 事件在此对齐；
 *  3. 页面从后台切回前台 / 网络恢复时立即重连，不等退避计时器；
 *  4. 30s 心跳 ping，穿透 nginx 60s 空闲断连，避免「看似连着实则已死」。
 */
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const HEARTBEAT_MS = 30000;

export function useWs() {
  const token = useAuth((s) => s.token);
  const setBalance = useAuth((s) => s.setBalance);
  const refreshBalance = useAuth((s) => s.refreshBalance);

  // 用 ref 持有最新回调，避免它们进 effect 依赖导致连接被反复重建
  const cbRef = useRef({ setBalance, refreshBalance });
  cbRef.current = { setBalance, refreshBalance };

  useEffect(() => {
    if (!token) return;

    let disposed = false;
    let ws: WebSocket | null = null;
    let retry = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

    const clearTimers = () => {
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
    };

    const scheduleReconnect = () => {
      if (disposed || reconnectTimer) return;
      // 指数退避 + 抖动，避免服务端重启时全体客户端同时重连造成惊群
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** retry, RECONNECT_MAX_MS);
      const jitter = Math.random() * 0.3 * delay;
      retry += 1;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay + jitter);
    };

    const connect = () => {
      if (disposed) return;
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      let sock: WebSocket;
      try {
        sock = new WebSocket(`${proto}://${location.host}/ws`);
      } catch {
        scheduleReconnect();
        return;
      }
      ws = sock;

      sock.onopen = () => {
        if (disposed) { sock.close(); return; }
        retry = 0;
        sock.send(JSON.stringify({ type: 'auth', token }));
        // 关键兜底：补齐断连期间丢失的 balance.changed（首连时也顺带对齐一次）
        cbRef.current.refreshBalance();
        heartbeatTimer = setInterval(() => {
          if (sock.readyState === WebSocket.OPEN) {
            try { sock.send(JSON.stringify({ type: 'ping' })); } catch { /* 下个 onclose 会重连 */ }
          }
        }, HEARTBEAT_MS);
      };

      sock.onmessage = (ev) => {
        try {
          const e = JSON.parse(ev.data);
          if (e.kind === 'balance.changed') cbRef.current.setBalance(e.balance);
          else if (e.kind === 'job.updated' || e.kind === 'notification') {
            window.dispatchEvent(new CustomEvent('pea:event', { detail: e }));
          }
        } catch {
          /* ignore */
        }
      };

      sock.onclose = () => {
        if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
        if (!disposed) scheduleReconnect();
      };
      // onerror 后浏览器必定紧跟 onclose，重连交给 onclose 统一处理，避免重复排程
      sock.onerror = () => { /* noop */ };
    };

    // 回到前台 / 网络恢复：立刻重连并对齐余额，不等退避计时器走完
    const reviveNow = () => {
      if (disposed) return;
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        // 连接仍活着，只补一次余额（后台期间可能错过事件）
        if (ws.readyState === WebSocket.OPEN) cbRef.current.refreshBalance();
        return;
      }
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      retry = 0;
      connect();
    };
    const onVisible = () => { if (document.visibilityState === 'visible') reviveNow(); };

    connect();
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('online', reviveNow);

    return () => {
      disposed = true;
      clearTimers();
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('online', reviveNow);
      if (ws) {
        ws.onclose = null; // 主动关闭不触发重连
        ws.close();
      }
    };
  }, [token]);
}
