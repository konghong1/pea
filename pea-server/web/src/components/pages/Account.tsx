import { useEffect, useState } from 'react';
import { Card, Avatar, Spin, Table, Tag, Empty, Switch, Button, App, Input, Select } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { api } from '../../api/client';
import { useAuth } from '../../store/auth';
import { useUi, type AccountPane } from '../../store/ui';
import { toast } from '../../store/toast';

/* ───────────────────────── 类型 ───────────────────────── */
interface Profile {
  id: number;
  email: string;
  display_name: string;
  avatar_url: string | null;
  created_at: string;
}
interface LedgerRow {
  id: number;
  type: 'preauth' | 'confirm' | 'refund' | 'grant';
  debit: number;
  credit: number;
  balance_after: number;
  created_at: string;
}
interface Provider {
  id: string;
  name: string;
  kind: 'image' | 'video' | 'text' | 'audio';
  enabled: boolean;
  isDefault: boolean;
  config: any;
}
const KIND_COLOR: Record<Provider['kind'], string> = {
  image: 'purple',
  video: 'blue',
  text: 'green',
  audio: 'orange',
};

/* ─────────────────── 账户中心 7 面板导航 ─────────────────── */
const NAV: { group: string; items: { key: AccountPane; label: string }[] }[] = [
  {
    group: '个人设置',
    items: [
      { key: 'profile', label: '资料设置' },
      { key: 'general', label: '通用设置' },
      { key: 'aiprov', label: 'AI 提供商' },
    ],
  },
  {
    group: '订阅和充值',
    items: [
      { key: 'billing', label: '权益和账单' },
      { key: 'invite', label: '邀请好友' },
      { key: 'notif', label: '我的通知' },
    ],
  },
  {
    group: '帮助与支持',
    items: [{ key: 'support', label: '帮助与支持' }],
  },
];

const TYPE_META: Record<string, { color: string; text: string }> = {
  grant: { color: 'purple', text: '赠送' },
  preauth: { color: 'red', text: '预扣' },
  confirm: { color: 'default', text: '确认' },
  refund: { color: 'green', text: '退还' },
};

/** 账户中心 (T-M5-01)：单一账户页 + 左 7 项导航 + 7 面板，对齐 pea-canvas-v12.html `.acct-layout`。 */
export default function Account() {
  const initialPane = useUi((s) => s.accountPane);
  const [pane, setPane] = useState<AccountPane>(initialPane);
  // 从 UserMenu 深层链接切换面板（如「AI Provider 设置」直达 aiprov）
  useEffect(() => setPane(initialPane), [initialPane]);

  const { user } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get('/users/me').then((r) => setProfile((r.data as Profile) ?? null)).catch(() => {}),
      api.get('/billing/balance').then((r) => setBalance((r.data as any)?.balance ?? 0)).catch(() => {}),
      api
        .get('/billing/ledger?page=1&size=20')
        .then((r) => setLedger((r.data as LedgerRow[]) ?? []))
        .catch(() => {}),
    ]).finally(() => setLoading(false));
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

  const displayName = profile?.display_name || user?.displayName || '用户';
  const email = profile?.email || user?.email || '';

  return (
    <div className="pea-page pea-acct">
      {/* 账户页头：头像 / 名称 / 邮箱 / 积分余额 */}
      <header className="acct-header">
        <div className="acct-header-left">
          <Avatar size={46} style={{ background: 'var(--pea-brand)', flexShrink: 0 }}>
            {displayName?.[0]?.toUpperCase()}
          </Avatar>
          <div className="acct-header-meta">
            <div className="acct-header-name">{displayName}</div>
            <div className="acct-header-mail">{email}</div>
          </div>
        </div>
        <div className="acct-balance-chip">
          <span className="acct-balance-ico">💎</span>
          <span className="acct-balance-num">{balance ?? 0}</span>
          <span className="acct-balance-unit">Tapies</span>
        </div>
      </header>

      <div className="acct-layout">
        {/* 左导航 */}
        <nav className="acct-side">
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="acct-nav-group">{g.group}</div>
              {g.items.map((it) => (
                <div
                  key={it.key}
                  className={`acct-nav${pane === it.key ? ' active' : ''}`}
                  data-pane={it.key}
                  onClick={() => setPane(it.key)}
                >
                  {it.label}
                </div>
              ))}
            </div>
          ))}
        </nav>

        {/* 右内容 */}
        <div className="acct-content">
          {pane === 'profile' && (
            <ProfilePane
              profile={profile}
              displayName={displayName}
              email={email}
              ledger={ledger}
            />
          )}
          {pane === 'general' && <GeneralPane />}
          {pane === 'aiprov' && <ProviderPane />}
          {pane === 'billing' && <BillingPane balance={balance} ledger={ledger} />}
          {pane === 'invite' && <InvitePane email={email} />}
          {pane === 'notif' && <NotifPane />}
          {pane === 'support' && <SupportPane />}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════ 资料设置 ══════════════════════ */
function ProfilePane({
  profile,
  displayName,
  email,
  ledger,
}: {
  profile: Profile | null;
  displayName: string;
  email: string;
  ledger: LedgerRow[];
}) {
  const [nick, setNick] = useState(profile?.display_name || displayName);
  const [bio, setBio] = useState('I am turning imagination into reality.');
  const [mail, setMail] = useState(profile?.email || email);

  const save = () => {
    try {
      localStorage.setItem('pea_account', JSON.stringify({ nick, bio, mail }));
    } catch {}
    toast.success('资料已更新');
  };

  return (
    <section className="acct-pane active">
      <h3 className="acct-pane-title">资料设置</h3>
      <div className="acct-avatar-row">
        <div className="acct-avatar">{(nick || 'U')?.[0]?.toUpperCase()}</div>
        <button className="acct-link-btn" onClick={() => toast.info('更换头像（演示）')}>
          更换头像
        </button>
      </div>
      <div className="acct-field">
        <label>用户名</label>
        <Input className="acct-input" value={nick} onChange={(e) => setNick(e.target.value)} />
      </div>
      <div className="acct-field">
        <label>个人简介</label>
        <Input.TextArea
          className="acct-input"
          rows={3}
          value={bio}
          onChange={(e) => setBio(e.target.value)}
        />
      </div>
      <div className="acct-field">
        <label>邮箱</label>
        <Input className="acct-input" value={mail} onChange={(e) => setMail(e.target.value)} />
      </div>
      <Button type="primary" className="acct-save" onClick={save}>
        保存
      </Button>

      {/* 最近积分流水预览（E8 默认面板需可见「积分流水」） */}
      <div className="acct-sub-card" style={{ marginTop: 28 }}>
        <div className="acct-sub-meta" style={{ marginBottom: 10, fontWeight: 600 }}>
          积分流水（最近 {Math.min(5, ledger.length)} 条）
        </div>
        {ledger.length === 0 ? (
          <Empty description="暂无流水" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="acct-mini-ledger">
            {ledger.slice(0, 5).map((r) => (
              <div className="acct-mini-row" key={r.id}>
                <Tag color={TYPE_META[r.type]?.color} style={{ marginInlineEnd: 8 }}>
                  {TYPE_META[r.type]?.text}
                </Tag>
                <span className="acct-mini-amount">
                  {r.credit > 0 ? (
                    <b style={{ color: '#2f9e44' }}>+{r.credit}</b>
                  ) : r.debit > 0 ? (
                    <b style={{ color: '#e03131' }}>-{r.debit}</b>
                  ) : (
                    '—'
                  )}
                </span>
                <span className="acct-mini-time">{new Date(r.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

/* ══════════════════════ 通用设置 ══════════════════════ */
const LANGS = ['简体中文', 'English', '日本語', '한국어'];
function GeneralPane() {
  const [lang, setLang] = useState<string>(() => {
    try {
      return JSON.parse(localStorage.getItem('pea_general') || '{}').lang || '简体中文';
    } catch {
      return '简体中文';
    }
  });
  const save = () => {
    try {
      localStorage.setItem('pea_general', JSON.stringify({ lang }));
    } catch {}
    toast.success('通用设置已保存');
  };
  return (
    <section className="acct-pane active">
      <h3 className="acct-pane-title">通用设置</h3>
      <div className="acct-field">
        <label>语言</label>
        <Select
          className="acct-input"
          value={lang}
          style={{ width: '100%' }}
          onChange={(v) => setLang(v)}
          options={LANGS.map((l) => ({ value: l, label: l }))}
        />
      </div>
      <Button type="primary" className="acct-save" onClick={save}>
        保存
      </Button>
    </section>
  );
}

/* ════════════════ AI 提供商（复用 /providers API） ════════════════ */
function ProviderPane() {
  const { message } = App.useApp();
  const [list, setList] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api
      .get('/providers')
      .then((r) => setList((r.data as Provider[]) ?? []))
      .catch(() => message.error('加载 Provider 失败'))
      .finally(() => setLoading(false));
  }, [message]);

  const toggle = async (p: Provider) => {
    setBusy(p.id);
    try {
      await api.patch(`/providers/${p.id}`, { enabled: !p.enabled });
      setList((l) => l.map((x) => (x.id === p.id ? { ...x, enabled: !x.enabled } : x)));
    } catch {
      message.error('更新失败');
    } finally {
      setBusy(null);
    }
  };
  const setDefault = async (p: Provider) => {
    setBusy(p.id);
    try {
      await api.patch(`/providers/${p.id}`, { isDefault: true });
      setList((l) => l.map((x) => ({ ...x, isDefault: x.id === p.id })));
      message.success(`已将 ${p.name} 设为默认`);
    } catch {
      message.error('设置默认失败');
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <section className="acct-pane active">
        <h3 className="acct-pane-title">限制项目 AI 提供商配置</h3>
        <div style={{ marginTop: 24 }}>
          <Spin />
        </div>
      </section>
    );
  }

  return (
    <section className="acct-pane active">
      <h3 className="acct-pane-title">限制项目 AI 提供商配置</h3>
      <p className="acct-hint">
        为当前项目限定可使用的模型提供商；关闭后，该项目生成将不会调用对应服务。
      </p>
      <div className="pea-card-grid" style={{ marginTop: 18 }}>
        {list.map((p) => (
          <Card
            key={p.id}
            styles={{ body: { padding: 18 } }}
            className="pea-card"
            style={{ borderColor: p.isDefault ? 'var(--pea-brand)' : undefined }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ color: 'var(--pea-brand)', fontWeight: 600 }}>{p.name}</span>
                  {p.isDefault && (
                    <Tag color="purple" style={{ marginInlineEnd: 0 }}>
                      默认
                    </Tag>
                  )}
                </div>
                <div style={{ marginTop: 8 }}>
                  <Tag color={KIND_COLOR[p.kind]}>{p.kind}</Tag>
                </div>
              </div>
              <Switch
                checked={p.enabled}
                loading={busy === p.id}
                onChange={() => toggle(p)}
                aria-label={`启用 ${p.name}`}
              />
            </div>
            <div style={{ marginTop: 16 }}>
              <Button
                size="small"
                type={p.isDefault ? 'default' : 'primary'}
                disabled={p.isDefault || busy === p.id}
                onClick={() => setDefault(p)}
              >
                {p.isDefault ? '当前默认' : '设为默认'}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
}

/* ══════════════════════ 权益和账单 ══════════════════════ */
function BillingPane({ balance, ledger }: { balance: number | null; ledger: LedgerRow[] }) {
  return (
    <section className="acct-pane active">
      <h3 className="acct-pane-title">权益和账单</h3>
      <div className="acct-sub-card">
        <div className="acct-sub-plan">🎁 免费版</div>
        <div className="acct-sub-meta">
          当前套餐：Free · 积分余额 <b>{balance ?? 0}</b> Tapies
        </div>
      </div>
      <div className="acct-bill-grid">
        <div className="acct-bill-item">
          <div className="abt">订阅套餐</div>
          <button className="acct-link-btn" onClick={() => toast.info('打开订阅套餐 💎')}>
            查看
          </button>
        </div>
        <div className="acct-bill-item">
          <div className="abt">充值积分</div>
          <button className="acct-link-btn" onClick={() => toast.info('打开充值积分')}>
            充值
          </button>
        </div>
        <div className="acct-bill-item">
          <div className="abt">账单记录</div>
          <button className="acct-link-btn" onClick={() => toast.info('打开账单记录')}>
            查看
          </button>
        </div>
        <div className="acct-bill-item">
          <div className="abt">用量看板</div>
          <button className="acct-link-btn" onClick={() => toast.info('打开用量看板')}>
            查看
          </button>
        </div>
      </div>

      <div className="acct-sub-meta" style={{ margin: '26px 0 12px', fontWeight: 600 }}>
        积分流水
      </div>
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
    </section>
  );
}

/* ══════════════════════ 邀请好友 ══════════════════════ */
function InvitePane({ email }: { email: string }) {
  const link = `https://pea.ai/invite/${encodeURIComponent(email || 'user')}`;
  const copy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(link);
        toast.success('邀请链接已复制');
        return;
      }
    } catch {}
    toast.info('复制失败，请手动复制');
  };
  return (
    <section className="acct-pane active">
      <h3 className="acct-pane-title">邀请好友</h3>
      <p className="acct-hint">
        把你的作品发布到 TapTV 后将会获得大量奖励支持，若作品 70% 以上由 pea 完成，最高可获得 2w 积分的奖励。
      </p>
      <div className="acct-field">
        <label>邀请链接</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <Input className="acct-input" value={link} readOnly />
          <Button icon={<CopyOutlined />} className="acct-link-btn" onClick={copy}>
            复制链接
          </Button>
        </div>
      </div>
      <div className="acct-sub-card">
        <div className="acct-sub-meta">邀请记录</div>
        <div className="acct-stat-row">
          <div>
            <div className="acct-stat-num">0</div>
            <div className="acct-stat-lbl">已邀请</div>
          </div>
          <div>
            <div className="acct-stat-num">0</div>
            <div className="acct-stat-lbl">已奖励(积分)</div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ══════════════════════ 我的通知 ══════════════════════ */
const NOTIF_DEFS = [
  { id: 'email', ico: '✉️', name: '邮件通知', desc: '重要动态通过邮件提醒' },
  { id: 'inbox', ico: '📥', name: '站内消息', desc: '系统消息与私信' },
  { id: 'done', ico: '✅', name: '创作完成提醒', desc: '套图 / 视频生成完成时通知' },
  { id: 'social', ico: '💬', name: '社区互动', desc: '点赞、评论、关注提醒' },
  { id: 'promo', ico: '🎁', name: '营销活动', desc: '新功能与活动推送' },
];
function NotifPane() {
  const [state, setState] = useState<Record<string, boolean>>(() => {
    try {
      const r = JSON.parse(localStorage.getItem('pea_notif') || '{}');
      const d: Record<string, boolean> = {};
      NOTIF_DEFS.forEach((n) => (d[n.id] = r[n.id] !== false));
      return d;
    } catch {
      const d: Record<string, boolean> = {};
      NOTIF_DEFS.forEach((n) => (d[n.id] = true));
      return d;
    }
  });
  const toggle = (id: string) => setState((s) => ({ ...s, [id]: !s[id] }));
  const save = () => {
    try {
      localStorage.setItem('pea_notif', JSON.stringify(state));
    } catch {}
    toast.success('通知偏好已保存');
  };
  return (
    <section className="acct-pane active">
      <h3 className="acct-pane-title">我的通知</h3>
      <div className="notif-list">
        {NOTIF_DEFS.map((n) => (
          <div className="notif-row" key={n.id}>
            <div className="nr-ico">{n.ico}</div>
            <div className="nr-info">
              <div className="nr-name">{n.name}</div>
              <div className="nr-desc">{n.desc}</div>
            </div>
            <Switch checked={!!state[n.id]} onChange={() => toggle(n.id)} aria-label={`通知 ${n.name}`} />
          </div>
        ))}
      </div>
      <Button type="primary" className="acct-save" onClick={save}>
        保存通知偏好
      </Button>
    </section>
  );
}

/* ══════════════════════ 帮助与支持 ══════════════════════ */
const SUPPORT_ITEMS = [
  { name: '使用教程', act: '打开使用教程' },
  { name: '帮助中心', act: '打开帮助中心' },
  { name: '快捷键', act: '打开快捷键' },
  { name: '反馈问题', act: '打开反馈' },
  { name: '加入 Discord 社群', act: '打开 Discord' },
  { name: '联系我们', act: '打开联系我们' },
];
function SupportPane() {
  return (
    <section className="acct-pane active">
      <h3 className="acct-pane-title">帮助与支持</h3>
      <div className="acct-bill-grid">
        {SUPPORT_ITEMS.map((s) => (
          <div className="acct-bill-item" key={s.name}>
            <div className="abt">{s.name}</div>
            <button className="acct-link-btn" onClick={() => toast.info(s.act)}>
              {s.name.startsWith('加入') ? '加入' : '打开'}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
