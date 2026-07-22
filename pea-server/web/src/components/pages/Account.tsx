import { useEffect, useState } from 'react';
import { Card, Avatar, Spin, Table, Tag, Empty } from 'antd';
import { WalletOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import { useAuth } from '../../store/auth';

interface Profile {
  id: number;
  email: string;
  display_name: string;
  avatar_url: string | null;
  created_at: string;
}
interface LedgerRow {
  id: number;
  type: 'preauth' | 'confirm' | 'refund';
  debit: number;
  credit: number;
  balance_after: number;
  created_at: string;
}

const TYPE_META: Record<string, { color: string; text: string }> = {
  preauth: { color: 'red', text: '预扣' },
  confirm: { color: 'default', text: '确认' },
  refund: { color: 'green', text: '退还' },
};

/** 账户中心 (T-M5-01 / PRD §10)：资料 + 余额 + 积分流水。 */
export default function Account() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get('/users/me').then((r) => setProfile(r.data)),
      api.get('/billing/balance').then((r) => setBalance(r.data.balance)),
      api.get('/billing/ledger?page=1&size=20').then((r) => setLedger(r.data ?? [])),
    ])
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="pea-page">
        <div className="pea-page-pad">
          <Spin />
        </div>
      </div>
    );
  }

  return (
    <div className="pea-page">
      <div className="pea-page-pad">
        <div className="pea-hero-title">账户中心</div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16, marginTop: 20 }}>
          {/* 资料卡 */}
          <Card className="pea-card" styles={{ body: { padding: 20 } }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <Avatar size={56} style={{ background: '#6c5ce7' }}>
                {(profile?.display_name || user?.displayName || 'U')?.[0]?.toUpperCase()}
              </Avatar>
              <div>
                <div style={{ fontWeight: 600, fontSize: 16 }}>{profile?.display_name || user?.displayName}</div>
                <div className="pea-muted" style={{ fontSize: 13 }}>{profile?.email}</div>
              </div>
            </div>
            <div className="pea-muted" style={{ fontSize: 12, marginTop: 14 }}>
              注册于 {profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : '-'}
            </div>
          </Card>

          {/* 余额卡 */}
          <Card className="pea-card" styles={{ body: { padding: 20 } }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }} className="pea-muted">
              <WalletOutlined /> 账户余额
            </div>
            <div style={{ fontSize: 34, fontWeight: 700, color: '#6c5ce7', marginTop: 6 }}>
              {balance ?? 0} <span style={{ fontSize: 15, fontWeight: 500 }}>Tapies</span>
            </div>
          </Card>
        </div>

        {/* 积分流水 */}
        <div className="pea-muted" style={{ marginTop: 28, fontWeight: 600, color: '#444' }}>
          积分流水
        </div>
        <div style={{ marginTop: 12 }}>
          {ledger.length === 0 ? (
            <Card className="pea-card">
              <Empty description="暂无流水" />
            </Card>
          ) : (
            <Table<LedgerRow>
              rowKey="id"
              dataSource={ledger}
              pagination={false}
              size="middle"
              columns={[
                {
                  title: '类型',
                  dataIndex: 'type',
                  width: 100,
                  render: (t: string) => <Tag color={TYPE_META[t]?.color}>{TYPE_META[t]?.text}</Tag>,
                },
                {
                  title: '扣减',
                  dataIndex: 'debit',
                  width: 100,
                  render: (v: number) => (v > 0 ? <span style={{ color: '#e03131' }}>-{v}</span> : '-'),
                },
                {
                  title: '增加',
                  dataIndex: 'credit',
                  width: 100,
                  render: (v: number) => (v > 0 ? <span style={{ color: '#2f9e44' }}>+{v}</span> : '-'),
                },
                { title: '余额', dataIndex: 'balance_after', width: 100 },
                {
                  title: '时间',
                  dataIndex: 'created_at',
                  render: (t: string) => new Date(t).toLocaleString(),
                },
              ]}
            />
          )}
        </div>
      </div>
    </div>
  );
}
