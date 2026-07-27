import { App, Button, Select, Tooltip } from 'antd';
import { ShareAltOutlined, WalletOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import { useAuth } from '../store/auth';
import { useTheme } from '../store/theme';
import { useUi, PageKey } from '../store/ui';
import { toast } from '../store/toast';
import NotificationCenter from './NotificationCenter';
import UserMenu from './UserMenu';

const NAV: { key: PageKey; label: string }[] = [
  { key: 'home', label: '主页' },
  { key: 'workspace', label: '工作空间' },
  { key: 'ecom', label: '电商套图' },
  { key: 'tvtv', label: 'TapTV' },
  { key: 'arena', label: '竞技场' },
];

/** 顶部全局导航 (FR-G1)：Logo + 导航项 + 积分/分享/通知/主题/用户。 */
export default function TopNav() {
  const { balance, setBalance } = useAuth();
  const { mode, setMode } = useTheme();
  const { active, setActive } = useUi();
  const { message } = App.useApp();

  // 余额由常驻的 Workspace 通过 refreshMe 同步（Workspace 已含静默续期 + 30 分钟保活）。
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
        <Select
          className="pea-theme-select"
          value={mode}
          onChange={(v) => setMode(v)}
          suffixIcon={<span className="text-xs">▾</span>}
          options={[
            { label: '浅色', value: 'light' },
            { label: '深色', value: 'dark' },
            { label: '跟随系统', value: 'system' },
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
