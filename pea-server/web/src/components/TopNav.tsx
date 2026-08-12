import { App, Select, Tooltip } from 'antd';
import { ShareAltOutlined, DownOutlined, TeamOutlined } from '@ant-design/icons';
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
  const { balance, refreshBalance } = useAuth();
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
          <img src="/logo.svg" alt="pea" className="h-7 w-7 rounded-lg" />
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
          <button
            type="button"
            className="pea-topnav-balance"
            aria-label={`Tapies 余额 ${balance}`}
            onClick={() => void refreshBalance()}
          >
            {/* 能量光球图标（圆形） */}
            <svg className="pea-balance-gem" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
              <defs>
                <radialGradient id="topnavOrbBg" cx="40%" cy="35%" r="60%">
                  <stop offset="0%" stopColor="#c4b5fd"/>
                  <stop offset="50%" stopColor="#a78bfa"/>
                  <stop offset="100%" stopColor="#5B7BF5"/>
                </radialGradient>
                <linearGradient id="topnavOrbShine" x1="6" y1="4" x2="18" y2="16">
                  <stop offset="0%" stopColor="rgba(255,255,255,0.75)"/>
                  <stop offset="100%" stopColor="rgba(255,255,255,0)"/>
                </linearGradient>
                <filter id="topnavOrbGlow">
                  <feGaussianBlur stdDeviation="1" result="blur"/>
                  <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
              </defs>
              {/* 外层光晕 */}
              <circle cx="14" cy="14" r="12" fill="url(#topnavOrbBg)" filter="url(#topnavOrbGlow)" opacity="0.3"/>
              {/* 主球体 */}
              <circle cx="14" cy="14" r="10" fill="url(#topnavOrbBg)"/>
              {/* 上方高光弧 */}
              <path d="M7 11A7 7 0 0 1 21 11" stroke="url(#topnavOrbShine)" strokeWidth="2" strokeLinecap="round" fill="none"/>
              {/* 左上小高光点 */}
              <circle cx="10" cy="9.5" r="1.8" fill="rgba(255,255,255,0.55)"/>
              {/* 中心星芒 */}
              <path d="M14 7L14.8 10.2L18 11L14.8 11.8L14 15L13.2 11.8L10 11L13.2 10.2Z" fill="rgba(255,255,255,0.9)"/>
            </svg>
            <span className="pea-balance-num">{balance}</span>
          </button>
        </Tooltip>
        <button type="button" className="pea-topnav-community" onClick={() => toast.info('社区功能即将开放')}>
          <TeamOutlined /> 社区
        </button>
        <Tooltip title="复制分享链接">
          <button type="button" className="pea-topnav-share" aria-label="复制分享链接" onClick={onShare}>
            <ShareAltOutlined />
          </button>
        </Tooltip>
        <NotificationCenter />
        <Select
          className="pea-theme-select"
          value={mode}
          onChange={(v) => setMode(v)}
          suffixIcon={<DownOutlined />}
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
