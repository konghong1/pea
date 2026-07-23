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
  { key: 'ecom', label: '电商套图' },
  { key: 'tvtv', label: 'TapTV' },
  { key: 'arena', label: '竞技场' },
];

function relTime(ts: number): string {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return '刚刚';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

/** 顶部全局导航 (FR-G1)：Logo + 画布标题 + 导航项 + 积分/分享/通知/主题/用户。 */
export default function TopNav() {
  const { balance, setBalance } = useAuth();
  const { mode, setMode } = useTheme();
  const { active, setActive } = useUi();
  const title = useCanvas((s) => s.title);
  const dirty = useCanvas((s) => s.dirty);
  const lastSavedAt = useCanvas((s) => s.lastSavedAt);
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
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-pea-purple via-pea-brand to-pea-lime shadow-sm" />
          <span className="font-semibold">pea</span>
        </div>
        {active === 'canvas' && title && (
          <div className="hidden items-center gap-2 border-l border-black/10 pl-3 dark:border-white/10 md:flex">
            <span className="text-sm font-medium">{title}</span>
            <span className="text-xs text-gray-400">
              {dirty ? '编辑中…' : lastSavedAt ? `上次修改于 ${relTime(lastSavedAt)}` : '工作空间'}
            </span>
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
        <Button type="text" size="small" onClick={() => toast.info('社区功能即将开放')}>
          ✦ 社区
        </Button>
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
        <button className="pea-trial-btn" aria-label="免费体验" onClick={() => toast.success('已为你开放 7 天 Pro 体验 ✦')}>
          免费体验
        </button>
      </div>
    </header>
  );
}
