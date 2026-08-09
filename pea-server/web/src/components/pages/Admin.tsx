import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  RateLimitRule,
  adminListRateLimits,
  adminCreateRateLimit,
  adminUpdateRateLimit,
  adminDeleteRateLimit,
} from '../../api/admin';
import type { PlanView, PricingRule } from '../../api/catalog';
import { AdminOrdersPane, AdminQrcodesPane } from './AdminPaymentsPane';
import PricingEditor from '../admin/PricingEditor';
import {
  toFormValue,
  toWire,
  validateForm,
  summarizePricing,
  type PricingFormValue,
} from '../admin/pricingForm';

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
          统一配置 AI 提供商、模型与定价、上游速率限制、售卖套餐。密钥仅存内网库，对外一律脱敏。
        </p>
        <Tabs
          defaultActiveKey="providers"
          items={[
            { key: 'providers', label: 'AI 提供商', children: <ProvidersPane /> },
            { key: 'models', label: '模型 & 定价', children: <ModelsPane /> },
            { key: 'ratelimits', label: '速率限制', children: <RateLimitsPane /> },
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

const PROVIDER_KINDS = ['image', 'video', 'text', 'audio', '3d'] as const;

// 系统支持的厂商目录 —— 前端下拉仅列这些, 用户无需理解协议/厂商概念。
// 选定厂商后 protocol / vendor 由后台按映射定死 (见下方 SUPPORTED_VENDORS)。
// 每接入一家新厂商, 在此加一行即可; 后端需先实现对应适配器 (provider_adapter 注册)。
const SUPPORTED_VENDORS = [
  {
    value: 'agnes',
    label: 'Agnes',
    protocol: 'openai-compatible',
    vendor: 'agnes',
    defaultId: 'agnes',
    defaultName: 'Agnes AI',
  },
  {
    value: 'minimax',
    label: 'MiniMax',
    protocol: 'vendor-native',
    vendor: 'minimax',
    defaultId: 'minimax',
    defaultName: 'MiniMax 海螺',
  },
  {
    value: 'volcengine',
    label: '火山方舟 Volcengine',
    protocol: 'openai-compatible',
    vendor: 'volcengine',
    defaultId: 'volcengine',
    defaultName: '火山方舟 Volcengine',
  },
  {
    value: 'gemini',
    label: 'Google Gemini',
    protocol: 'vendor-native',
    vendor: 'gemini',
    defaultId: 'gemini',
    defaultName: 'Google Gemini',
  },
] as const;

// 厂商 value → 展示名 (用于列表标签; 兼容历史记录里未列出的厂商原样显示)。
const VENDOR_LABEL: Record<string, string> = {
  agnes: 'Agnes',
  minimax: 'MiniMax',
  volcengine: 'Volcengine',
  gemini: 'Gemini',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
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
      title: '厂商',
      width: 160,
      render: (_: any, r: ProviderView) => (
        <Tag color="geekblue">{VENDOR_LABEL[r.vendor] ?? r.vendor ?? r.protocol}</Tag>
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
    { title: '主类型', dataIndex: 'kind', width: 80, render: (v) => <Tag>{v}</Tag> },
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
    const sel = record ? SUPPORTED_VENDORS.find((x) => x.vendor === record.vendor) : undefined;
    form.setFieldsValue({
      id: record?.id ?? '',
      name: record?.name ?? '',
      protocol: record?.protocol ?? 'openai-compatible',
      vendor: record?.vendor ?? '',
      vendorSel: sel?.value,
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
    // vendorSel 为内部派生字段, 不提交给后端
    delete v.vendorSel;
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
        {/* 协议/厂商由所选厂商定死, 作为隐藏字段随表单提交 */}
        <Form.Item name="protocol" hidden>
          <Input />
        </Form.Item>
        <Form.Item name="vendor" hidden>
          <Input />
        </Form.Item>
        <Form.Item
          label="厂商"
          name="vendorSel"
          tooltip="系统支持的厂商；选定后协议与厂商由后台按映射自动定死，无需手动选择"
          rules={[{ required: true, message: '请选择厂商' }]}
        >
          <Select
            options={SUPPORTED_VENDORS.map((v) => ({ value: v.value, label: v.label }))}
            placeholder="选择我们支持的厂商"
            onChange={(val: string) => {
              const pick = SUPPORTED_VENDORS.find((x) => x.value === val);
              if (!pick) return;
              const patch: Record<string, string> = {
                protocol: pick.protocol,
                vendor: pick.vendor,
              };
              if (!isEdit) {
                patch.id = pick.defaultId;
                patch.name = pick.defaultName;
              }
              form.setFieldsValue(patch);
            }}
          />
        </Form.Item>
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
          label="Base URL"
          name="baseUrl"
          tooltip="MiniMax 请填到域名为止（端点横跨 /v1 与 /v2，由适配器自行拼版本号）；Gemini 填 https://generativelanguage.googleapis.com 即可（可带 /v1beta），其余由适配器拼装"
        >
          <Input placeholder="https://apihub.agnes-ai.com/v1 或 https://api.minimaxi.com 或 https://generativelanguage.googleapis.com" />
        </Form.Item>
        <Form.Item
          label="API Key"
          name="apiKey"
          tooltip={isEdit ? '留空表示不修改既有密钥' : undefined}
          extra={isEdit && record?.hasApiKey ? `当前：${record.apiKeyMasked}（留空不改）` : undefined}
        >
          <Input.Password placeholder={isEdit ? '留空则保留原密钥' : 'sk-...'} autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          label="主类型"
          name="kind"
          tooltip="仅展示用，不影响该厂商下多模型并存（如火山可同时有文/图/视频模型）"
        >
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

const MODEL_TYPES = ['image', 'video', 'text', 'audio', '3d'] as const;

// 远端模型能力类型 → 中文标签 / antd Tag 颜色 (与后端 provider_remote_models.model_type 对齐)
const REMOTE_TYPE_LABEL: Record<string, string> = {
  image: '图像',
  video: '视频',
  text: '文本',
  audio: '音乐',
  embedding: '嵌入',
  '3d': '3D',
};
const REMOTE_TYPE_COLOR: Record<string, string> = {
  image: 'magenta',
  video: 'purple',
  text: 'blue',
  audio: 'cyan',
  embedding: 'green',
};
// ai_models.model_type 仅支持这三类, 远端模型若被推断为 audio/embedding 则不自动回填类型。
const COMPATIBLE_MODEL_TYPES = ['image', 'video', 'text', 'audio', '3d'];

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
  const text = summarizePricing(pricing);
  return (
    <span style={{ fontSize: 12 }} title={text}>
      💎 {text}
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

  // 定价不走 antd Form（它是一棵结构化的树，不是单个字段），单独持有受控状态。
  const [pricingForm, setPricingForm] = useState<PricingFormValue>(() =>
    toFormValue(record?.pricing ?? null, record?.paramsSchema ?? null, record?.modelType ?? 'image'),
  );
  // 新建模型且管理员尚未动过定价时，切换模型类型可自动套用该类型的推荐维度；
  // 一旦动过就不再覆盖，避免辛苦配好的档位被一次误点清空。
  const pricingTouched = useRef(false);
  const onPricingChange = useCallback((v: PricingFormValue) => {
    pricingTouched.current = true;
    setPricingForm(v);
  }, []);

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
    const order = ['image', 'video', 'text', 'audio', 'embedding', '3d'];
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
    });
    pricingTouched.current = false;
    setPricingForm(
      toFormValue(
        record?.pricing ?? null,
        record?.paramsSchema ?? null,
        record?.modelType ?? 'image',
      ),
    );
  }, [record, providers, form]);

  const modelType = Form.useWatch('modelType', form);
  useEffect(() => {
    if (isEdit || pricingTouched.current || !modelType) return;
    setPricingForm(toFormValue(null, null, modelType));
  }, [modelType, isEdit]);

  const submit = async () => {
    let v: any;
    try {
      v = await form.validateFields();
    } catch {
      return;
    }
    // 定价来自可视化编辑器：先做人话校验，再序列化成 pricing + paramsSchema 两份 JSON。
    // 客户端校验只为即时反馈；结构合法性与数值边界由服务端 DTO + normalizeRule 再兜一层，
    // 最终价永远由服务端 PricingService 计算。
    const pricingErrors = validateForm(pricingForm);
    if (pricingErrors.length) {
      message.error(pricingErrors[0]);
      return;
    }
    const { pricing, paramsSchema } = toWire(pricingForm);
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
        paramsSchema,
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
      width={900}
      style={{ top: 40 }}
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
            <Select options={MODEL_TYPES.map((t) => ({ value: t, label: REMOTE_TYPE_LABEL[t] || t }))} />
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
        <PricingEditor value={pricingForm} onChange={onPricingChange} />
        <Form.Item label="描述" name="description" style={{ marginTop: 12 }}>
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

/* ══════════════════════════ 速率限制 ══════════════════════════ */

/** 图像分辨率档位 —— 与编排器 param_adapters._TIER_TO_PIXELS 保持一致。 */
const SIZE_TIERS = ['1K', '2K', '3K', '4K'] as const;

/** 常用窗口预设，避免手输秒数出错。 */
const WINDOW_PRESETS = [
  { value: 60, label: '每 1 分钟' },
  { value: 300, label: '每 5 分钟' },
  { value: 3600, label: '每 1 小时' },
  { value: 86400, label: '每 1 天' },
];

function windowLabel(s: number): string {
  const hit = WINDOW_PRESETS.find((p) => p.value === s);
  if (hit) return hit.label;
  if (s % 3600 === 0) return `每 ${s / 3600} 小时`;
  if (s % 60 === 0) return `每 ${s / 60} 分钟`;
  return `每 ${s} 秒`;
}

/**
 * 上游厂商配额的可视化配置。
 *
 * 这些规则是编排器分布式令牌桶（Redis 固定窗口）的唯一数据源：改完 30s 内自动生效，
 * 无需重启编排器。作用是把 429 挡在请求发出之前，而不是撞上去再退避重试烧额度。
 */
function RateLimitsPane() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<RateLimitRule[]>([]);
  const [providers, setProviders] = useState<ProviderView[]>([]);
  const [models, setModels] = useState<ModelView[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<RateLimitRule | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, p, m] = await Promise.all([
        adminListRateLimits(),
        adminListProviders(),
        adminListModels(),
      ]);
      setRows(r);
      setProviders(p);
      setModels(m);
    } catch {
      message.error('加载速率限制规则失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  const providerName = useCallback(
    (id: string) => providers.find((p) => p.id === id)?.name ?? id,
    [providers],
  );

  const onDelete = async (r: RateLimitRule) => {
    try {
      await adminDeleteRateLimit(r.id);
      message.success('已删除');
      void load();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '删除失败');
    }
  };

  const onToggle = async (r: RateLimitRule, enabled: boolean) => {
    try {
      await adminUpdateRateLimit(r.id, { enabled });
      void load();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '更新失败');
    }
  };

  const columns: ColumnsType<RateLimitRule> = [
    {
      title: '提供商',
      dataIndex: 'provider_id',
      render: (v) => <b>{providerName(v)}</b>,
    },
    {
      title: '模型',
      dataIndex: 'model_id',
      render: (v) =>
        v ? <code>{v}</code> : <Tag color="blue">全部模型</Tag>,
    },
    {
      title: '档位',
      dataIndex: 'tier',
      width: 110,
      render: (v) => (v ? <Tag color="purple">{v}</Tag> : <Tag color="default">全部档位</Tag>),
    },
    {
      title: '配额',
      key: 'quota',
      width: 190,
      render: (_, r) => (
        <span>
          <b>{r.limit_n}</b> 次 / {windowLabel(r.window_s)}
        </span>
      ),
    },
    {
      title: '生效',
      dataIndex: 'enabled',
      width: 80,
      render: (v, r) => <Switch size="small" checked={v} onChange={(c) => void onToggle(r, c)} />,
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
          <Popconfirm
            title={`删除 ${providerName(r.provider_id)} 的这条限流规则?`}
            onConfirm={() => onDelete(r)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <div
        style={{
          marginBottom: 12,
          padding: '10px 14px',
          borderRadius: 10,
          background: 'var(--pea-bg-2, rgba(0,0,0,0.03))',
          border: '1px solid var(--pea-border, rgba(0,0,0,0.06))',
          fontSize: 13,
          lineHeight: 1.7,
          color: 'var(--pea-text-2, #555)',
        }}
      >
        按上游厂商公布的配额建规则，编排器会在<b>发请求前</b>用令牌桶拦住超额请求（多副本共享同一配额），
        而不是撞出 429 再重试烧额度。匹配优先级：
        <code>（厂商+模型+档位）&gt;（厂商+模型）&gt;（厂商+档位）&gt;（厂商）</code>，命中即用，不叠加。
        改完 <b>30 秒内自动生效</b>，无需重启服务。
      </div>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
          新建规则
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void load()}>
          刷新
        </Button>
      </Space>
      <Table<RateLimitRule>
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={rows}
        columns={columns}
        pagination={false}
        locale={{
          emptyText: (
            <Empty description="暂无限流规则（当前不限速，可能撞上游 429）" />
          ),
        }}
      />
      {(creating || editing) && (
        <RateLimitModal
          record={editing}
          providers={providers}
          models={models}
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

function RateLimitModal({
  record,
  providers,
  models,
  onClose,
  onSaved,
}: {
  record: RateLimitRule | null;
  providers: ProviderView[];
  models: ModelView[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [providerId, setProviderId] = useState<string | undefined>(record?.provider_id);
  const isEdit = !!record;

  useEffect(() => {
    form.setFieldsValue({
      provider_id: record?.provider_id,
      model_id: record?.model_id ?? undefined,
      tier: record?.tier ?? undefined,
      limit_n: record?.limit_n ?? 1,
      window_s: record?.window_s ?? 60,
      enabled: record?.enabled ?? true,
    });
    setProviderId(record?.provider_id);
  }, [record, form]);

  // 模型下拉随所选提供商联动，避免跨厂商错配。
  const modelOptions = useMemo(
    () =>
      models
        .filter((m) => !providerId || m.providerId === providerId)
        .map((m) => ({ value: m.id, label: `${m.displayName || m.id}（${m.modelType}）` })),
    [models, providerId],
  );

  const submit = async () => {
    let v: any;
    try {
      v = await form.validateFields();
    } catch {
      return;
    }
    setSaving(true);
    try {
      const dto = {
        provider_id: v.provider_id,
        model_id: v.model_id || null,
        tier: v.tier || null,
        limit_n: v.limit_n,
        window_s: v.window_s,
        enabled: v.enabled,
      };
      if (isEdit) await adminUpdateRateLimit(record!.id, dto);
      else await adminCreateRateLimit(dto);
      message.success('已保存，30 秒内生效');
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
      title={isEdit ? '编辑限流规则' : '新建限流规则'}
      onCancel={onClose}
      onOk={submit}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      destroyOnClose
    >
      <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
        <Form.Item
          label="提供商"
          name="provider_id"
          rules={[{ required: true, message: '请选择提供商' }]}
        >
          <Select
            placeholder="选择提供商"
            options={providers.map((p) => ({ value: p.id, label: `${p.name}（${p.kind}）` }))}
            onChange={(v) => {
              setProviderId(v);
              form.setFieldValue('model_id', undefined);
            }}
          />
        </Form.Item>
        <Form.Item
          label="模型"
          name="model_id"
          tooltip="留空 = 该提供商下所有模型共享同一个桶；选定 = 只约束这个模型"
        >
          <Select allowClear placeholder="（留空 = 全部模型）" options={modelOptions} />
        </Form.Item>
        <Form.Item
          label="分辨率档位"
          name="tier"
          tooltip="仅图像有效。留空 = 所有档位共享一个桶；选 4K = 只约束 4K 请求"
        >
          <Select
            allowClear
            placeholder="（留空 = 全部档位）"
            options={SIZE_TIERS.map((t) => ({ value: t, label: t }))}
          />
        </Form.Item>
        <Space style={{ display: 'flex' }} align="start" size={12}>
          <Form.Item
            label="允许次数"
            name="limit_n"
            style={{ width: 130 }}
            rules={[{ required: true, message: '必填' }]}
          >
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            label="时间窗口"
            name="window_s"
            style={{ flex: 1, minWidth: 190 }}
            rules={[{ required: true, message: '必填' }]}
            tooltip="必须对齐上游公布的窗口，否则拦不住"
          >
            <Select
              options={WINDOW_PRESETS}
              popupMatchSelectWidth={false}
              showSearch={false}
            />
          </Form.Item>
        </Space>
        <Form.Item label="启用" name="enabled" valuePropName="checked">
          <Switch />
        </Form.Item>
        <div style={{ fontSize: 12, color: 'var(--pea-text-3, #888)', lineHeight: 1.7 }}>
          例：Agnes 4K 档限 1 次/分钟 → 提供商选 Agnes、模型留空、档位选 <code>4K</code>、
          允许次数 <code>1</code>、窗口 <code>每 1 分钟</code>。
        </div>
      </Form>
    </Modal>
  );
}
