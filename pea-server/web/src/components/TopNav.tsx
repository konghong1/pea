import { useEffect } from 'react';
import { App, Button, Segmented, Tooltip } from 'antd';
import { ShareAltOutlined, WalletOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import { useAuth } from '../store/auth';
import { useTheme } from '../store/theme';
import { useUi, PageKey } from '../store/ui';
import { useCanvas } from '../store/canvas';
import { toast } from '../store/toast';
import NotificationCenter from './NotificationCenter';
import UserMenu from './UserMenu';

const NAV: { key: PageKey; label: string }[] = [
  { key: 'home', label: '主页' },
  { key: 'canvas', label: '工作空间' },
  { key: 'account', label: '账户' },
  { key: 'settings', label: '设置' },
  { key: 'tvtv', label: 'TapTV' },
  { key: 'arena', label: '竞技场' },
];

/** 顶部全局导航 (FR-G1)：Logo + 画布标题 + 导航项 + 积分/分享/通知/主题/用户。 */
export default function TopNav() {
  const { balance, setBalance } = useAuth();
  const { mode, setMode } = useTheme();
  const { active, setActive } = useUi();
  const title = useCanvas((s) => s.title);
  const { message } = App.useApp();

  useEffect(() => {
    api
      .get('/billing/balance')
      .then((r) => setBalance(r.data.balance))
      .catch(() => {});
  }, [setBalance]);

  const onShare = async () => {
    const url = window.location.href;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(url);
      } else {
        const ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        if (!ok) throw new Error('copy failed');
      }
      toast.success('链接已复制到剪贴板');
    } catch {
      toast.error('复制失败，请手动复制');
      message.info(url);
    }
  };

  return (
    <header className="pea-topnav">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-pea-brand to-pea-accent" />
          <span className="font-semibold">pea</span>
        </div>
        {active === 'canvas' && title && (
          <div className="hidden items-center gap-2 border-l border-black/10 pl-3 dark:border-white/10 md:flex">
            <span className="text-sm font-medium">{title}</span>
            <span className="text-xs text-gray-400">工作空间</span>
          </div>
        )}
      </div>

      <nav className="pea-nav">
        {NAV.map((n) => (
          <button
            key={n.key}
            className={`pea-nav-item${active === n.key ? ' active' : ''}`}
            onClick={() => setActive(n.key)}
          >
            {n.label}
          </button>
        ))}
      </nav>

      <div className="flex items-center gap-2">
        <Tooltip title="账户余额 (Tapies)">
          <Button
            icon={<WalletOutlined />}
            onClick={() => api.get('/billing/balance').then((r) => setBalance(r.data.balance))}
          >
            {balance} Tapies
          </Button>
        </Tooltip>
        <Tooltip title="复制分享链接">
          <Button type="text" shape="circle" aria-label="复制分享链接" icon={<ShareAltOutlined />} onClick={onShare} />
        </Tooltip>
        <NotificationCenter />
        <Segmented
          value={mode}
          onChange={(v) => setMode(v as any)}
          options={[
            { label: '浅', value: 'light' },
            { label: '深', value: 'dark' },
            { label: '跟随', value: 'system' },
          ]}
        />
        <UserMenu />
      </div>
    </header>
  );
}
