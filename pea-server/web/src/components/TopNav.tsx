import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Avatar, Button, Dropdown, Segmented, Tooltip } from 'antd';
import { LogoutOutlined, WalletOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import { useAuth } from '../store/auth';
import { useTheme } from '../store/theme';

export default function TopNav() {
  const { user, balance, setBalance, logout } = useAuth();
  const { mode, setMode } = useTheme();
  const navigate = useNavigate();
  const { message } = App.useApp();

  useEffect(() => {
    api
      .get('/billing/balance')
      .then((r) => setBalance(r.data.balance))
      .catch(() => {});
  }, [setBalance]);

  const onLogout = () => {
    logout();
    message.success('已退出');
    navigate('/login');
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-black/5 px-4 dark:border-white/10">
      <div className="flex items-center gap-2">
        <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-pea-brand to-pea-accent" />
        <span className="font-semibold">pea</span>
      </div>

      <div className="flex items-center gap-3">
        <Tooltip title="账户余额 (Tapies)">
          <Button icon={<WalletOutlined />} onClick={() => api.get('/billing/balance').then((r) => setBalance(r.data.balance))}>
            {balance} Tapies
          </Button>
        </Tooltip>

        <Segmented
          value={mode}
          onChange={(v) => setMode(v as any)}
          options={[
            { label: '浅', value: 'light' },
            { label: '深', value: 'dark' },
            { label: '跟随', value: 'system' },
          ]}
        />

        <Dropdown
          menu={{
            items: [
              { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: onLogout },
            ],
          }}
        >
          <Avatar>{user?.displayName?.[0]?.toUpperCase() ?? 'U'}</Avatar>
        </Dropdown>
      </div>
    </header>
  );
}
