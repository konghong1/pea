import { useState } from 'react';
import { Avatar, Dropdown } from 'antd';
import { useAuth } from '../store/auth';
import { useUi } from '../store/ui';
import { toast } from '../store/toast';

function UserCard({ name }: { name: string }) {
  return (
    <div className="pea-user-card">
      <div className="pea-user-name">{name}</div>
      <div className="pea-user-stats">
        <span><b>0</b> 作品</span>
        <span><b>0</b> 关注者</span>
        <span><b>0</b> 关注中</span>
      </div>
    </div>
  );
}

/** 顶栏用户菜单 (FR-M5-07)：头像下拉，含用户统计与全功能入口。 */
export default function UserMenu() {
  const { user, logout } = useAuth();
  const setActive = useUi((s) => s.setActive);
  const setAccountPane = useUi((s) => s.setAccountPane);
  const [open, setOpen] = useState(false);
  const soon = (name: string) => () => {
    setOpen(false);
    toast.info(`${name} 即将开放`);
  };
  const goAccount = (pane: 'profile' | 'aiprov') => () => {
    setOpen(false);
    setAccountPane(pane);
    setActive('account');
  };

  const items = [
    { key: 'card', label: <UserCard name={user?.displayName ?? '用户'} />, disabled: true },
    { type: 'divider' as const },
    { key: 'account', label: '账户中心', onClick: goAccount('profile') },
    { key: 'settings', label: 'AI Provider 设置', onClick: goAccount('aiprov') },
    { key: 'profile', label: '个人主页', onClick: soon('个人主页') },
    { key: 'notif', label: '通知', onClick: () => setOpen(false) },
    { type: 'divider' as const },
    { key: 'gift', label: '礼包超市', onClick: soon('礼包超市') },
    { key: 'sub', label: '订阅', onClick: soon('订阅') },
    { type: 'divider' as const },
    { key: 'tutorial', label: '使用教程', onClick: soon('使用教程') },
    { key: 'help', label: '帮助中心', onClick: soon('帮助中心') },
    { key: 'shortcut', label: '快捷键', onClick: soon('快捷键') },
    { key: 'feedback', label: '反馈', onClick: soon('反馈') },
    { key: 'discord', label: 'Discord', onClick: soon('Discord') },
    { key: 'contact', label: '联系我们', onClick: soon('联系我们') },
    { type: 'divider' as const },
    {
      key: 'logout',
      label: '退出登录',
      danger: true,
      onClick: () => {
        setOpen(false);
        logout();
        window.location.href = '/login';
      },
    },
  ];

  return (
    <Dropdown
      open={open}
      onOpenChange={setOpen}
      menu={{ items }}
      trigger={['click']}
      placement="bottomRight"
    >
      <div className="pea-user-trigger">
        <Avatar>{user?.displayName?.[0]?.toUpperCase() ?? 'U'}</Avatar>
      </div>
    </Dropdown>
  );
}
