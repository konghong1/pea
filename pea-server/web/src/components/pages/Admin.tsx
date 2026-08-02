import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  App,
  AutoComplete,
  Button,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Result,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
} from 'antd';
import {
  CloudDownloadOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useAuth } from '../../store/auth';
import { useUi } from '../../store/ui';
import {
  ProviderView,
  ModelView,
  RemoteModel,
  adminListProviders,
  adminCreateProvider,
  adminUpdateProvider,
  adminDeleteProvider,
  adminFetchRemoteModels,
  adminListRemoteModels,
  adminListModels,
  adminCreateModel,
  adminUpdateModel,
  adminDeleteModel,
  adminListPlans,
  adminUpsertPlan,
  adminDeletePlan,
} from '../../api/admin';
import type { PlanView, PricingRule } from '../../api/catalog';
import { AdminOrdersPane, AdminQrcodesPane } from './AdminPaymentsPane';

/**
 * 管理员控制台 (Phase 4)：AI 提供商 / 模型(动态定价) / 套餐 的可视化 CRUD。
 * 访问控制单一真源在服务端 (AdminGuard 查 users.role)，前端仅据 isAdmin 决定是否展示，
 * 即使绕过前端直接调 /admin/* 也会被后端 403 拦截。
 */
export default function Admin() {
  const isAdmin = useAuth((s) => s.isAdmin);
  const setActive = useUi((s) => s.setActive);

  if (!isAdmin) {
    return (
      <div className="pea-page">
        <div className="pea-page-pad">
          <Result
            status="403"
            title="无权限"
            subTitle="该控制台仅管理员可见。如需权限请联系平台管理员。"
            extra={
              <Button type="primary" onClick={() => setActive('workspace')}>
                返回工作空间
              </Button>
            }
          />
        </div>
      </div>
    );
  }

  return (
    <div className="pea-page">
      <div className="pea-page-pad" style={{ maxWidth: 1180, margin: '0 auto', width: '100%' }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>管理员控制台</h2>
        <p style={{ color: 'var(--pea-text-3, #888)', marginBottom: 18 }}>
          统一配置 AI 提供商、模型与定价、售卖套餐。密钥仅存内网库，对外一律脱敏。
        </p>
        <Tabs
          defaultActiveKey="providers"
          items={[
            { key: 'providers', label: 'AI 提供商', children: <ProvidersPane /> },
            { key: 'models', label: '模型 & 定价', children: <ModelsPane /> },
            { key: 'plans', label: '套餐', children: <PlansPane /> },
            { key: 'orders', label: '支付订单', children: <AdminOrdersPane /> },
            { key: 'qrcodes', label: '收款码', children: <AdminQrcodesPane /> },
          ]}
        />
      </div>
    </div>
  );
}

/* ══════════════════════════ 提供商 ══════════════════════════ */

const PROVIDER_KINDS = ['image', 'video', 'text', 'audio'] as const;

// 适配器类型 —— 必须与后端 app/providers 下 @register_provider 的注册名逐字一致，
// 否则编排器会回退到 openai-compatible 并在调用时报出难以定位的协议错误。
const PROVIDER_TYPE_OPTIONS = [
  { value: 'openai-compatible', label: 'openai-compatible（Agnes / OpenAI 兼容）' },
  { value: 'minimax', label: 'minimax（视频 v2+v1 / 图像 / 文本 / 音乐 / 语音）' },
  { value: 'anthropic-compatible', label: 'anthropic-compatible（Anthropic Messages 协议）' },
  { value: 'mock', label: 'mock（本地占位，不出网）' },
];

const PROVIDER_TYPE_COLOR: Record<string, string> = {
  'openai-compatible': 'blue',
  minimax: 'volcano',
  'anthropic-compatible': 'geekblue',
  mock: 'default',
};

function ProvidersPane() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<ProviderView[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<ProviderView | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [remoteFor, setRemoteFor] = useState<ProviderView | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await adminListProviders());
    } catch {
      message.error('加载提供商失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  const onToggle = async (p: ProviderView, enabled: boolean) => {
    setBusyId(p.id);
    try {
      await adminUpdateProvider(p.id, { enabled });
      setRows((l) => l.map((x) => (x.id === p.id ? { ...x, enabled } : x)));
    } catch {
      message.error('更新失败');
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async (p: ProviderView) => {
    try {
      await adminDeleteProvider(p.id);
      message.success('已删除');
      void load();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '删除失败（该提供商下可能仍有模型）');
    }
  };

  const onFetchModels = (p: ProviderView) => {
    setRemoteFor(p);
  };

  const columns: ColumnsType<ProviderView> = [
    {
      title: '名称',
      dataIndex: 'name',
      render: (v, r) => (
        <Space size={6}>
          <b>{v}</b>
          {r.isDefault && <Tag color="purple">默认</Tag>}
        </Space>
      ),
    },
    { title: 'ID', dataIndex: 'id', width: 120 },
    {
      title: '类型',
      dataIndex: 'providerType',
      width: 190,
      render: (v: string) => (
        <Tag color={PROVIDER_TYPE_COLOR[v] ?? 'default'} style={{ marginInlineEnd: 0 }}>
          {v}
        </Tag>
      ),
    },
    {
      title: 'Base URL',
      dataIndex: 'baseUrl',
      ellipsis: true,
      render: (v) => v || <span style={{ color: '#bbb' }}>—</span>,
    },
    {
      title: '密钥',
      dataIndex: 'apiKeyMasked',
      width: 150,
      render: (v, r) =>
        r.hasApiKey ? <code>{v}</code> : <Tag color="orange">未配置</Tag>,
    },
    { title: '媒介', dataIndex: 'kind', width: 80, render: (v) => <Tag>{v}</Tag> },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (v, r) => (
        <Switch
          size="small"
          checked={v}
          loading={busyId === r.id}
          onChange={(c) => onToggle(r, c)}
        />
      ),
    },
    {
      title: '操作',
      key: 'act',
      width: 240,
      render: (_, r) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<CloudDownloadOutlined />}
            onClick={() => onFetchModels(r)}
            title="查看该提供商的远端模型（按类型分组），可重新拉取"
          >
            模型
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(r)}>
            编辑
          </Button>
          <Popconfirm title={`删除提供商 ${r.name}?`} onConfirm={() => onDelete(r)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
          新建提供商
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>
          刷新
        </Button>
      </Space>
      <Table<ProviderView>
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={false}
        locale={{ emptyText: <Empty description="暂无提供商" /> }}
      />
      {(creating || editing) && (
        <ProviderModal
          record={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            void load();
          }}
        />
      )}
      {remoteFor && (
        <RemoteModelsModal provider={remoteFor} onClose={() => setRemoteFor(null)} />
      )}
    </>
  );
}

function RemoteModelsModal({
  provider,
  onClose,
}: {
  provider: ProviderView;
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const [models, setModels] = useState<RemoteModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);

  // 打开即加载「已持久化」的远端模型 (不需实时联网, 与 ai-agent 一致)。
  const loadStored = useCallback(async () => {
    setLoading(true);
    try {
      setModels(await adminListRemoteModels(provider.id));
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '读取已存模型失败');
    } finally {
      setLoading(false);
    }
  }, [provider.id, message]);

  useEffect(() => {
    void loadStored();
  }, [loadStored]);

  // 重新拉取: 实时从提供商拉取并按类型落库, 再刷新已存视图。
  const handleRefetch = async () => {
    if (!provider.baseUrl) return message.warning('该提供商未配置 baseUrl');
    setFetching(true);
    try {
      const ms = await adminFetchRemoteModels(provider.id);
      setModels(ms);
      message.success(`已重新拉取并保存 ${ms.length} 个远端模型`);
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '拉取远端模型失败');
    } finally {
      setFetching(false);
    }
  };

  // 按类型分组 (保留 provider_remote_models.model_type 的全部枚举顺序)。
  const groups = useMemo(() => {
    const order = ['text', 'image', 'video', 'audio', 'embedding'];
    const map = new Map<string, RemoteModel[]>();
    for (const m of models) {
      const t = m.modelType || 'unknown';
      if (!map.has(t)) map.set(t, []);
      map.get(t)!.push(m);
    }
    const entries = order.filter((t) => map.has(t)).map((t) => [t, map.get(t)!] as const);
    if (map.has('unknown')) entries.push(['unknown', map.get('unknown')!]);
    return entries;
  }, [models]);

  return (
    <Modal
      title={`${provider.name} · 远端模型`}
      open
      width={600}
      onCancel={onClose}
      footer={[
        <Button
          key="refetch"
          icon={<CloudDownloadOutlined />}
          loading={fetching}
          onClick={handleRefetch}
        >
          重新拉取
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>
          关闭
        </Button>,
      ]}
    >
      <div style={{ marginBottom: 12, color: '#888', fontSize: 12 }}>
        已持久化 {models.length} 个模型，按能力类型分组展示；点「重新拉取」从
        <code style={{ margin: '0 4px' }}>{provider.baseUrl || '未配置'}</code>
        实时刷新并保存。
      </div>
      {loading ? (
        <Empty description="加载中…" />
      ) : models.length === 0 ? (
        <Empty description="暂无已存模型，点「重新拉取」从提供商获取" />
      ) : (
        <div style={{ maxHeight: 440, overflow: 'auto', paddingRight: 4 }}>
          {groups.map(([t, list]) => (
            <div key={t} style={{ marginBottom: 14 }}>
              <div
                style={{
                  fontWeight: 600,
                  marginBottom: 6,
                  color: REMOTE_TYPE_COLOR[t] || '#333',
                }}
              >
                {REMOTE_TYPE_LABEL[t] || t}（{list.length}）
              </div>
              {list.map((m) => (
                <div
                  key={m.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '3px 0',
                  }}
                >
                  <code>{m.id}</code>
                  <Space size={6}>
                    <Tag color={REMOTE_TYPE_COLOR[m.modelType || ''] || 'default'}>
                      {REMOTE_TYPE_LABEL[m.modelType || ''] || m.modelType || '未知'}
                    </Tag>
                    {m.owned_by && <span style={{ color: '#999' }}>{m.owned_by}</span>}
                  </Space>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

function ProviderModal({
  record,
  onClose,
  onSaved,
}: {
  record: ProviderView | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const isEdit = !!record;

  useEffect(() => {
    form.setFieldsValue({
      id: record?.id ?? '',
      name: record?.name ?? '',
      providerType: record?.providerType ?? 'openai-compatible',
      baseUrl: record?.baseUrl ?? '',
      apiKey: '',
      kind: record?.kind ?? 'image',
      enabled: record?.enabled ?? true,
      isDefault: record?.isDefault ?? false,
    });
  }, [record, form]);

  const submit = async () => {
    let v: any;
    try {
      v = await form.validateFields();
    } catch {
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        // 编辑时不传空 apiKey，避免误清空既有密钥（后端亦有保护）。
        const { id: _id, apiKey, ...rest } = v;
        await adminUpdateProvider(record!.id, {
          ...rest,
          ...(apiKey ? { apiKey } : {}),
        });
      } else {
        await adminCreateProvider(v);
      }
      message.success('已保存');
      onSaved();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      title={isEdit ? `编辑提供商 · ${record!.name}` : '新建提供商'}
      onCancel={onClose}
      onOk={submit}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      destroyOnClose
    >
      <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
        <Form.Item
          label="ID"
          name="id"
          rules={[
            { required: !isEdit, message: '请输入 ID' },
            { pattern: /^[a-z0-9][a-z0-9_-]{1,63}$/i, message: '仅字母数字与 _-，2~64 位' },
          ]}
        >
          <Input placeholder="如 agnes" disabled={isEdit} />
        </Form.Item>
        <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入名称' }]}>
          <Input placeholder="展示名称" />
        </Form.Item>
        <Form.Item
          label="提供商类型"
          name="providerType"
          tooltip="决定后端用哪个适配器发请求，必须与上游实际协议一致，选错会直接 4xx"
        >
          <Select options={PROVIDER_TYPE_OPTIONS} />
        </Form.Item>
        <Form.Item
          label="Base URL"
          name="baseUrl"
          tooltip="MiniMax 请填到域名为止（端点横跨 /v1 与 /v2，由适配器自行拼版本号）"
        >
          <Input placeholder="https://apihub.agnes-ai.com/v1 或 https://api.minimaxi.com" />
        </Form.Item>
        <Form.Item
          label="API Key"
          name="apiKey"
          tooltip={isEdit ? '留空表示不修改既有密钥' : undefined}
          extra={isEdit && record?.hasApiKey ? `当前：${record.apiKeyMasked}（留空不改）` : undefined}
        >
          <Input.Password placeholder={isEdit ? '留空则保留原密钥' : 'sk-...'} autoComplete="new-password" />
        </Form.Item>
        <Form.Item label="默认媒介" name="kind">
          <Select options={PROVIDER_KINDS.map((k) => ({ value: k, label: k }))} />
        </Form.Item>
        <Space size={32}>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="设为默认" name="isDefault" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Space>
      </Form>
    </Modal>
  );
}

/* ══════════════════════════ 模型 & 定价 ══════════════════════════ */

const MODEL_TYPES = ['image', 'video', 'text'] as const;

// 远端模型能力类型 → 中文标签 / antd Tag 颜色 (与后端 provider_remote_models.model_type 对齐)
const REMOTE_TYPE_LABEL: Record<string, string> = {
  image: '图像',
  video: '视频',
  text: '文本',
  audio: '音频',
  embedding: '嵌入',
};
const REMOTE_TYPE_COLOR: Record<string, string> = {
  image: 'magenta',
  video: 'purple',
  text: 'blue',
  audio: 'cyan',
  embedding: 'green',
};
// ai_models.model_type 仅支持这三类, 远端模型若被推断为 audio/embedding 则不自动回填类型。
const COMPATIBLE_MODEL_TYPES = ['image', 'video', 'text'];

function ModelsPane() {
  const { message } = App.useApp();
  const [providers, setProviders] = useState<ProviderView[]>([]);
  const [rows, setRows] = useState<ModelView[]>([]);
  const [filter, setFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<ModelView | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ps, ms] = await Promise.all([adminListProviders(), adminListModels(filter)]);
      setProviders(ps);
      setRows(ms);
    } catch {
      message.error('加载模型失败');
    } finally {
      setLoading(false);
    }
  }, [filter, message]);

  useEffect(() => {
    void load();
  }, [load]);

  const providerName = useMemo(() => {
    const m = new Map(providers.map((p) => [p.id, p.name]));
    return (id: string) => m.get(id) ?? id;
  }, [providers]);

  const onDelete = async (m: ModelView) => {
    try {
      await adminDeleteModel(m.id);
      message.success('已删除');
      void load();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '删除失败');
    }
  };

  const columns: ColumnsType<ModelView> = [
    {
      title: '模型',
      dataIndex: 'displayName',
      render: (v, r) => (
        <Space size={6}>
          <b>{v}</b>
          {r.isDefault && <Tag color="purple">默认</Tag>}
          {!r.enabled && <Tag color="default">停用</Tag>}
        </Space>
      ),
    },
    { title: 'ID', dataIndex: 'id', width: 180, render: (v) => <code>{v}</code> },
    { title: '类型', dataIndex: 'modelType', width: 80, render: (v) => <Tag>{v}</Tag> },
    { title: '提供商', dataIndex: 'providerId', width: 120, render: (v) => providerName(v) },
    {
      title: '权益门槛',
      dataIndex: 'minPlanLevel',
      width: 90,
      render: (v) => (v > 0 ? <Tag color="gold">Lv.{v}</Tag> : <span style={{ color: '#bbb' }}>免费</span>),
    },
    {
      title: '定价',
      key: 'pricing',
      width: 200,
      render: (_, r) => <PricingSummary pricing={r.pricing} />,
    },
    {
      title: '操作',
      key: 'act',
      width: 150,
      render: (_, r) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(r)}>
            编辑
          </Button>
          <Popconfirm title={`删除模型 ${r.displayName}?`} onConfirm={() => onDelete(r)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 12 }} wrap>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
          新建模型
        </Button>
        <Select
          allowClear
          placeholder="按提供商筛选"
          style={{ width: 200 }}
          value={filter}
          onChange={(v) => setFilter(v)}
          options={providers.map((p) => ({ value: p.id, label: p.name }))}
        />
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>
          刷新
        </Button>
      </Space>
      <Table<ModelView>
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={false}
        locale={{ emptyText: <Empty description="暂无模型" /> }}
      />
      {(creating || editing) && (
        <ModelModal
          record={editing}
          providers={providers}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            void load();
          }}
        />
      )}
    </>
  );
}

function PricingSummary({ pricing }: { pricing: PricingRule | null }) {
  if (!pricing) return <span style={{ color: '#bbb' }}>默认</span>;
  const parts: string[] = [`基础 ${pricing.base ?? 10}`];
  if (pricing.tiers) {
    for (const [dim, table] of Object.entries(pricing.tiers)) {
      const items = Object.entries(table || {})
        .map(([k, v]) => `${k}+${v}`)
        .join(' ');
      if (items) parts.push(`${dim}: ${items}`);
    }
  }
  if (pricing.multiplier) parts.push(`×${pricing.multiplier}`);
  return (
    <span style={{ fontSize: 12 }} title={parts.join(' / ')}>
      💎 {parts.join(' · ')}
    </span>
  );
}

function ModelModal({
  record,
  providers,
  onClose,
  onSaved,
}: {
  record: ModelView | null;
  providers: ProviderView[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [remoteModels, setRemoteModels] = useState<RemoteModel[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const isEdit = !!record;

  // 监听「提供商」变化, 自动加载该提供商的远端模型清单 (按类型) 作为下拉选项。
  const providerId = Form.useWatch('providerId', form);
  const loadRemote = useCallback(
    async (pid?: string) => {
      if (!pid) {
        setRemoteModels([]);
        return;
      }
      try {
        setRemoteModels(await adminListRemoteModels(pid));
      } catch {
        setRemoteModels([]);
      }
    },
    [],
  );
  useEffect(() => {
    void loadRemote(providerId);
  }, [providerId, loadRemote]);

  // 远端模型按类型分组 (下拉可选项)
  const remoteOptions = useMemo(() => {
    const byType = new Map<string, RemoteModel[]>();
    for (const m of remoteModels) {
      const t = m.modelType || 'text';
      if (!byType.has(t)) byType.set(t, []);
      byType.get(t)!.push(m);
    }
    const order = ['image', 'video', 'text', 'audio', 'embedding'];
    return order
      .filter((t) => byType.has(t))
      .map((t) => ({
        label: `${REMOTE_TYPE_LABEL[t] || t}（${byType.get(t)!.length}）`,
        options: byType.get(t)!.map((m) => ({ value: m.id, label: m.id, modelType: m.modelType })),
      }));
  }, [remoteModels]);

  const onRefreshRemote = async () => {
    if (!providerId) {
      message.warning('请先选择提供商');
      return;
    }
    setRefreshing(true);
    try {
      const ms = await adminFetchRemoteModels(providerId);
      setRemoteModels(ms);
      message.success(`已拉取并保存 ${ms.length} 个远端模型`);
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '拉取远端模型失败');
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    form.setFieldsValue({
      id: record?.id ?? '',
      providerId: record?.providerId ?? providers[0]?.id ?? '',
      modelName: record?.modelName ?? '',
      displayName: record?.displayName ?? '',
      modelType: record?.modelType ?? 'image',
      minPlanLevel: record?.minPlanLevel ?? 0,
      enabled: record?.enabled ?? true,
      isDefault: record?.isDefault ?? false,
      sortOrder: record?.sortOrder ?? 0,
      description: record?.description ?? '',
      pricingText: record?.pricing
        ? JSON.stringify(record.pricing, null, 2)
        : JSON.stringify({ base: 10, tiers: { size: { '2K': 5, '4K': 20 } }, multiplier: 'n' }, null, 2),
    });
  }, [record, providers, form]);

  const submit = async () => {
    let v: any;
    try {
      v = await form.validateFields();
    } catch {
      return;
    }
    // 解析定价 JSON（客户端仅做结构校验；最终价永远由服务端 PricingService 计算）
    let pricing: PricingRule | null = null;
    const text = (v.pricingText ?? '').trim();
    if (text) {
      try {
        pricing = JSON.parse(text);
      } catch {
        message.error('定价 JSON 格式错误');
        return;
      }
    }
    setSaving(true);
    try {
      const payload = {
        providerId: v.providerId,
        modelName: v.modelName,
        displayName: v.displayName || v.modelName,
        modelType: v.modelType,
        minPlanLevel: v.minPlanLevel ?? 0,
        enabled: v.enabled,
        isDefault: v.isDefault,
        sortOrder: v.sortOrder ?? 0,
        description: v.description ?? '',
        pricing,
      };
      if (isEdit) {
        await adminUpdateModel(record!.id, payload);
      } else {
        await adminCreateModel({ id: v.id, ...payload });
      }
      message.success('已保存');
      onSaved();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      width={640}
      title={isEdit ? `编辑模型 · ${record!.displayName}` : '新建模型'}
      onCancel={onClose}
      onOk={submit}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      destroyOnClose
    >
      <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
        <Space style={{ display: 'flex' }} align="start" size={12}>
          <Form.Item
            label="模型 ID"
            name="id"
            style={{ flex: 1 }}
            rules={[{ required: !isEdit, message: '请输入模型 ID' }]}
            tooltip="平台内唯一标识，生成请求以此路由，如 agnes-image-2.0-flash"
          >
            <Input placeholder="agnes-image-2.0-flash" disabled={isEdit} />
          </Form.Item>
          <Form.Item
            label="提供商"
            name="providerId"
            style={{ width: 200 }}
            rules={[{ required: true, message: '请选择提供商' }]}
          >
            <Select options={providers.map((p) => ({ value: p.id, label: p.name }))} />
          </Form.Item>
        </Space>
        <Space style={{ display: 'flex' }} align="start" size={12}>
          <Form.Item
            label="远端模型名"
            name="modelName"
            style={{ flex: 1 }}
            rules={[{ required: true, message: '请选择或输入远端模型名' }]}
            tooltip="调用提供商时使用的真实 model 参数；可点「刷新远端模型」从提供商拉取后下拉选择（按类型分组）"
          >
            <AutoComplete
              placeholder="选择或输入，如 agnes-image-2.0-flash"
              options={remoteOptions}
              showSearch
              filterOption={(input, option: any) =>
                (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
              }
              onSelect={(_value, option: any) => {
                const t = option?.modelType;
                if (t && COMPATIBLE_MODEL_TYPES.includes(t)) {
                  form.setFieldValue('modelType', t);
                }
              }}
            />
          </Form.Item>
          <Button
            style={{ marginTop: 28 }}
            icon={<CloudDownloadOutlined />}
            loading={refreshing}
            onClick={onRefreshRemote}
          >
            刷新远端模型
          </Button>
          <Form.Item label="展示名" name="displayName" style={{ flex: 1 }}>
            <Input placeholder="用户可见名称" />
          </Form.Item>
        </Space>
        <Space style={{ display: 'flex' }} align="start" size={12} wrap>
          <Form.Item label="类型" name="modelType" style={{ width: 130 }}>
            <Select options={MODEL_TYPES.map((t) => ({ value: t, label: t }))} />
          </Form.Item>
          <Form.Item label="权益门槛" name="minPlanLevel" tooltip="用户生效权益等级 ≥ 此值才可调用" style={{ width: 130 }}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="排序" name="sortOrder" style={{ width: 100 }}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item label="默认" name="isDefault" valuePropName="checked" tooltip="同类型默认模型（用户未指定时使用）">
            <Switch />
          </Form.Item>
        </Space>
        <Form.Item
          label="定价 (pricing_json)"
          name="pricingText"
          tooltip="base 基础价；tiers 按参数加价（如 size 2K/4K）；multiplier 数量倍率参数名。最终价由服务端权威计算。"
        >
          <Input.TextArea rows={7} spellCheck={false} style={{ fontFamily: 'monospace', fontSize: 12 }} />
        </Form.Item>
        <Form.Item label="描述" name="description">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

/* ══════════════════════════ 套餐 ══════════════════════════ */

function PlansPane() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<PlanView[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<PlanView | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await adminListPlans());
    } catch {
      message.error('加载套餐失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  const onDelete = async (p: PlanView) => {
    try {
      await adminDeletePlan(p.id);
      message.success('已删除');
      void load();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '删除失败');
    }
  };

  const columns: ColumnsType<PlanView> = [
    {
      title: '套餐',
      dataIndex: 'name',
      render: (v, r) => (
        <Space size={6}>
          <b>{v}</b>
          {!r.enabled && <Tag color="default">停用</Tag>}
        </Space>
      ),
    },
    { title: 'ID', dataIndex: 'id', width: 120, render: (v) => <code>{v}</code> },
    { title: '权益等级', dataIndex: 'planLevel', width: 90 },
    {
      title: '价格',
      dataIndex: 'priceCents',
      width: 110,
      render: (v) => (v > 0 ? `¥${(v / 100).toFixed(2)}` : <Tag color="green">免费</Tag>),
    },
    { title: '赠送 Tapies', dataIndex: 'tapies', width: 110, render: (v) => `💎 ${v}` },
    { title: '有效期(天)', dataIndex: 'durationDays', width: 100 },
    {
      title: '操作',
      key: 'act',
      width: 150,
      render: (_, r) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => setEditing(r)}>
            编辑
          </Button>
          <Popconfirm title={`删除套餐 ${r.name}?`} onConfirm={() => onDelete(r)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
          新建套餐
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>
          刷新
        </Button>
      </Space>
      <Table<PlanView>
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={false}
        locale={{ emptyText: <Empty description="暂无套餐" /> }}
      />
      {(creating || editing) && (
        <PlanModal
          record={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            setCreating(false);
            setEditing(null);
            void load();
          }}
        />
      )}
    </>
  );
}

function PlanModal({
  record,
  onClose,
  onSaved,
}: {
  record: PlanView | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const isEdit = !!record;

  useEffect(() => {
    form.setFieldsValue({
      id: record?.id ?? '',
      name: record?.name ?? '',
      planLevel: record?.planLevel ?? 1,
      priceYuan: record ? record.priceCents / 100 : 0,
      tapies: record?.tapies ?? 0,
      durationDays: record?.durationDays ?? 30,
      enabled: record?.enabled ?? true,
      sortOrder: record?.sortOrder ?? 0,
      featuresText: (record?.features ?? []).join('\n'),
    });
  }, [record, form]);

  const submit = async () => {
    let v: any;
    try {
      v = await form.validateFields();
    } catch {
      return;
    }
    setSaving(true);
    try {
      const features = String(v.featuresText ?? '')
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      await adminUpsertPlan({
        id: v.id,
        name: v.name || v.id,
        planLevel: v.planLevel ?? 1,
        priceCents: Math.round((v.priceYuan ?? 0) * 100),
        tapies: v.tapies ?? 0,
        durationDays: v.durationDays ?? 30,
        enabled: v.enabled,
        sortOrder: v.sortOrder ?? 0,
        features,
      });
      message.success('已保存');
      onSaved();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      title={isEdit ? `编辑套餐 · ${record!.name}` : '新建套餐'}
      onCancel={onClose}
      onOk={submit}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      destroyOnClose
    >
      <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
        <Space style={{ display: 'flex' }} align="start" size={12}>
          <Form.Item
            label="套餐 ID"
            name="id"
            style={{ flex: 1 }}
            rules={[{ required: true, message: '请输入套餐 ID' }]}
          >
            <Input placeholder="如 pro-monthly" disabled={isEdit} />
          </Form.Item>
          <Form.Item label="名称" name="name" style={{ flex: 1 }} rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="专业版（月）" />
          </Form.Item>
        </Space>
        <Space style={{ display: 'flex' }} align="start" size={12} wrap>
          <Form.Item label="权益等级" name="planLevel" tooltip="决定可解锁的模型门槛" style={{ width: 120 }}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="价格(元)" name="priceYuan" tooltip="0 元套餐不可购买（仅注册赠送）" style={{ width: 120 }}>
            <InputNumber min={0} step={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="赠送 Tapies" name="tapies" style={{ width: 130 }}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="有效期(天)" name="durationDays" tooltip="0 表示不过期" style={{ width: 120 }}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Space>
        <Space size={32}>
          <Form.Item label="排序" name="sortOrder">
            <InputNumber style={{ width: 120 }} />
          </Form.Item>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Space>
        <Form.Item label="权益点（每行一条）" name="featuresText">
          <Input.TextArea rows={4} placeholder={'解锁高清 4K\n视频生成\n优先队列'} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
