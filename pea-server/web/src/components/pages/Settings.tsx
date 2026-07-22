import { useEffect, useState } from 'react';
import { Card, Switch, Button, Tag, Spin, Empty, App } from 'antd';
import { StarFilled, ApiOutlined } from '@ant-design/icons';
import { api } from '../../api/client';

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

/** 设置页 · AI Provider 配置 (T-G-06 / T-M5-02 / FR-G7)：列表 / 开关 / 默认回退 / 持久化。 */
export default function Settings() {
  const { message } = App.useApp();
  const [list, setList] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api
      .get('/providers')
      .then((r) => setList(r.data ?? []))
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

  return (
    <div className="pea-page">
      <div className="pea-page-pad">
        <div className="pea-hero-title">AI Provider 设置</div>
        <p className="pea-muted" style={{ marginTop: 8 }}>
          管理可用模型来源，开关启用状态，并指定默认回退 Provider（生成管道失败自动切换）。
        </p>

        {loading ? (
          <div style={{ marginTop: 28 }}>
            <Spin />
          </div>
        ) : list.length === 0 ? (
          <div style={{ marginTop: 28 }}>
            <Empty description="暂无 Provider" />
          </div>
        ) : (
          <div className="pea-card-grid" style={{ marginTop: 24 }}>
            {list.map((p) => (
              <Card
                key={p.id}
                styles={{ body: { padding: 18 } }}
                className="pea-card"
                style={{ borderColor: p.isDefault ? '#6c5ce7' : undefined }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <ApiOutlined style={{ color: '#6c5ce7' }} />
                      <span style={{ fontWeight: 600, fontSize: 15 }}>{p.name}</span>
                      {p.isDefault && (
                        <Tag color="purple" icon={<StarFilled />} style={{ marginInlineEnd: 0 }}>
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
                    icon={<StarFilled />}
                    onClick={() => setDefault(p)}
                  >
                    {p.isDefault ? '当前默认' : '设为默认'}
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
