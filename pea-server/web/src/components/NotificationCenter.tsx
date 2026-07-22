import { useEffect } from 'react';
import { Badge, Button, Drawer, Empty } from 'antd';
import { BellOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useNotif, NotifLevel } from '../store/notifications';

const LEVEL_COLOR: Record<NotifLevel, string> = {
  info: '#00CEC9',
  success: '#52c41a',
  warning: '#faad14',
  error: '#ff4d4f',
};

let seeded = false;

/** 顶栏通知中心：铃铛 + 未读角标 + 列表抽屉，接 WS notification (FR-G6)。 */
export default function NotificationCenter() {
  const items = useNotif((s) => s.items);
  const unread = useNotif((s) => s.unread);
  const add = useNotif((s) => s.add);
  const markAllRead = useNotif((s) => s.markAllRead);
  const [open, setOpen] = useState(false);

  // 订阅 WS 通知事件
  useEffect(() => {
    const onEvent = (e: Event) => {
      const ev = (e as CustomEvent).detail;
      if (ev?.kind === 'notification') {
        add({
          title: ev.title ?? '通知',
          body: ev.body ?? '',
          level: ev.level ?? 'info',
          ts: ev.ts ?? Date.now(),
        });
      }
    };
    window.addEventListener('pea:event', onEvent);
    return () => window.removeEventListener('pea:event', onEvent);
  }, [add]);

  // 种子欢迎通知（模块级守卫避免 StrictMode 重复）
  useEffect(() => {
    if (seeded) return;
    if (useNotif.getState().items.length > 0) {
      seeded = true;
      return;
    }
    seeded = true;
    add({
      title: '欢迎来到 pea',
      body: '你的创作操作系统已就绪，开始你的第一个画布吧。',
      level: 'info',
      ts: Date.now(),
    });
  }, [add]);

  const openDrawer = () => {
    setOpen(true);
    markAllRead();
  };

  return (
    <>
      <Badge count={unread} size="small" offset={[-2, 2]}>
        <Button type="text" shape="circle" aria-label="通知中心" icon={<BellOutlined />} onClick={openDrawer} />
      </Badge>
      <Drawer title="通知中心" placement="right" onClose={() => setOpen(false)} open={open} width={360}>
        {items.length === 0 ? (
          <Empty description="暂无新通知" />
        ) : (
          <div className="pea-notif-list">
            {items.map((n) => (
              <div key={n.id} className={`pea-notif-item${n.read ? ' read' : ''}`}>
                <span className="pea-notif-dot" style={{ background: LEVEL_COLOR[n.level] }} />
                <div className="pea-notif-body">
                  <div className="pea-notif-title">{n.title}</div>
                  <div className="pea-notif-text">{n.body}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Drawer>
    </>
  );
}
