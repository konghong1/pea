import { useEffect } from 'react';
import { useAuth } from '../store/auth';

/**
 * 连接 BFF WebSocket (/ws), 鉴权后接收实时事件:
 *  - balance.changed -> 更新顶栏余额
 *  - job.updated / notification -> 派发 window CustomEvent 供组件订阅
 */
export function useWs() {
  const token = useAuth((s) => s.token);
  const setBalance = useAuth((s) => s.setBalance);

  useEffect(() => {
    if (!token) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }));
    ws.onmessage = (ev) => {
      try {
        const e = JSON.parse(ev.data);
        if (e.kind === 'balance.changed') setBalance(e.balance);
        else if (e.kind === 'job.updated' || e.kind === 'notification') {
          window.dispatchEvent(new CustomEvent('pea:event', { detail: e }));
        }
      } catch {
        /* ignore */
      }
    };
    return () => ws.close();
  }, [token, setBalance]);
}
