import { useCallback, useEffect, useState } from 'react';
import {
  App,
  Badge,
  Button,
  Card,
  Image,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Upload,
} from 'antd';
import {
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  PictureOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  adminApproveOrder,
  adminDeleteQrcode,
  adminListOrders,
  adminListQrcodes,
  adminRejectOrder,
  adminUpsertQrcode,
  loadImageBlob,
  uploadProofImage,
  yuan,
  type OrderView,
  type QrcodeView,
} from '../../api/orders';

const STATUS_COLOR: Record<string, string> = {
  pending: 'gold',
  submitted: 'processing',
  paid: 'success',
  rejected: 'error',
  cancelled: 'default',
  expired: 'default',
};

/**
 * 支付订单审核台。
 *
 * 人工确认路径的全部人力成本集中在这一屏：
 *   收款通知里看到 ¥19.87 → 在列表里按金额定位到唯一订单 → 比对截图 → 点「确认到账」
 * 「确认到账」是幂等操作（幂等键 = 订单号），重复点击不会重复发放。
 */
export function AdminOrdersPane() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<OrderView[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string>('submitted');
  const [keyword, setKeyword] = useState('');
  const [acting, setActing] = useState<string | null>(null);
  const [proofUrl, setProofUrl] = useState<string>('');
  const [proofOpen, setProofOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await adminListOrders(status, 100));
    } catch {
      message.error('加载订单失败');
    } finally {
      setLoading(false);
    }
  }, [status, message]);

  useEffect(() => {
    void load();
  }, [load]);

  const approve = async (o: OrderView) => {
    setActing(o.orderNo);
    try {
      const updated = await adminApproveOrder(o.orderNo);
      message.success(`已开通：${updated.planName} → ${o.userEmail ?? o.userId}`);
      void load();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '确认失败');
    } finally {
      setActing(null);
    }
  };

  const reject = async (o: OrderView, note: string) => {
    setActing(o.orderNo);
    try {
      await adminRejectOrder(o.orderNo, note || '未收到对应金额的付款');
      message.success('已驳回');
      void load();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '驳回失败');
    } finally {
      setActing(null);
    }
  };

  const viewProof = async (o: OrderView) => {
    try {
      const url = await loadImageBlob(`/admin/orders/${o.orderNo}/proof`);
      setProofUrl(url);
      setProofOpen(true);
    } catch {
      message.warning('该订单没有付款截图');
    }
  };

  const filtered = keyword.trim()
    ? rows.filter((r) => {
        const k = keyword.trim().toLowerCase();
        return (
          r.orderNo.toLowerCase().includes(k) ||
          (r.userEmail ?? '').toLowerCase().includes(k) ||
          (r.userName ?? '').toLowerCase().includes(k) ||
          yuan(r.payAmountCents).includes(k)
        );
      })
    : rows;

  const columns: ColumnsType<OrderView> = [
    {
      title: '应付金额',
      dataIndex: 'payAmountCents',
      width: 120,
      sorter: (a, b) => a.payAmountCents - b.payAmountCents,
      render: (v: number) => {
        const [i, d] = yuan(v).split('.');
        return (
          <span style={{ fontFamily: 'var(--pea-font-mono, monospace)', fontSize: 14 }}>
            ¥{i}.
            <b style={{ color: 'var(--pea-brand, #7f77dd)' }}>{d}</b>
          </span>
        );
      },
    },
    {
      title: '用户',
      width: 200,
      render: (_, r) => (
        <div style={{ lineHeight: 1.4 }}>
          <div style={{ fontSize: 13 }}>{r.userName || '-'}</div>
          <div style={{ fontSize: 11, color: 'var(--pea-text-3, #999)' }}>{r.userEmail}</div>
        </div>
      ),
    },
    {
      title: '套餐',
      width: 130,
      render: (_, r) => (
        <div style={{ lineHeight: 1.4 }}>
          <div style={{ fontSize: 13 }}>{r.planName}</div>
          <div style={{ fontSize: 11, color: 'var(--pea-text-3, #999)' }}>
            Lv.{r.planLevel} · 💎{r.tapies}
          </div>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (v: string, r) => (
        <>
          <Tag color={STATUS_COLOR[v] ?? 'default'}>{r.statusText}</Tag>
          {r.status === 'paid' && !r.granted && <Tag color="error">待补发</Tag>}
        </>
      ),
    },
    {
      title: '凭证 / 备注',
      width: 180,
      render: (_, r) => (
        <Space size={4} direction="vertical" style={{ lineHeight: 1.4 }}>
          {r.proofKey && (
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => viewProof(r)}>
              查看截图
            </Button>
          )}
          {r.proofNote && (
            <span style={{ fontSize: 12, color: 'var(--pea-text-3, #888)' }}>{r.proofNote}</span>
          )}
          {!r.proofKey && !r.proofNote && <span style={{ color: '#ccc' }}>—</span>}
        </Space>
      ),
    },
    {
      title: '下单时间',
      dataIndex: 'createdAt',
      width: 150,
      render: (v: string) => (
        <span style={{ fontSize: 12 }}>
          {v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-'}
        </span>
      ),
    },
    {
      title: '订单号',
      dataIndex: 'orderNo',
      width: 190,
      render: (v: string) => (
        <span style={{ fontFamily: 'var(--pea-font-mono, monospace)', fontSize: 11, color: '#999' }}>
          {v}
        </span>
      ),
    },
    {
      title: '操作',
      width: 170,
      fixed: 'right',
      render: (_, r) => {
        const canReview = ['pending', 'submitted'].includes(r.status) || (r.status === 'paid' && !r.granted);
        if (!canReview) return <span style={{ color: '#ccc' }}>—</span>;
        return (
          <Space size={4}>
            <Popconfirm
              title="确认已收到该笔款项？"
              description={`将立即为用户开通 ${r.planName}，并到账 ${r.tapies} Tapies`}
              okText="确认到账"
              cancelText="再看看"
              onConfirm={() => approve(r)}
            >
              <Button
                type="primary"
                size="small"
                icon={<CheckOutlined />}
                loading={acting === r.orderNo}
              >
                {r.status === 'paid' ? '补发权益' : '确认到账'}
              </Button>
            </Popconfirm>
            {r.status !== 'paid' && (
              <Popconfirm
                title="驳回该订单？"
                okText="驳回"
                cancelText="取消"
                onConfirm={() => reject(r, '')}
              >
                <Button size="small" danger icon={<CloseOutlined />} />
              </Popconfirm>
            )}
          </Space>
        );
      },
    },
  ];

  const submittedCount = rows.filter((r) => r.status === 'submitted').length;

  return (
    <div>
      <Space style={{ marginBottom: 14 }} wrap>
        <Segmented
          value={status}
          onChange={(v) => setStatus(v as string)}
          options={[
            { label: <Badge count={submittedCount} size="small" offset={[8, -2]}>待确认</Badge>, value: 'submitted' },
            { label: '待付款', value: 'pending' },
            { label: '已开通', value: 'paid' },
            { label: '全部', value: 'all' },
          ]}
        />
        <Input.Search
          allowClear
          placeholder="按金额 / 邮箱 / 订单号筛选"
          style={{ width: 260 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </Space>

      <div
        style={{
          fontSize: 12,
          color: 'var(--pea-text-3, #888)',
          marginBottom: 12,
          lineHeight: 1.7,
        }}
      >
        对账方式：收款通知里的金额尾数唯一对应一张订单（如 <b>¥19.87</b>），直接在上方搜索框输入金额即可定位。
        「确认到账」是幂等操作，重复点击不会重复发放。
      </div>

      <Table<OrderView>
        rowKey="orderNo"
        size="small"
        loading={loading}
        dataSource={filtered}
        columns={columns}
        scroll={{ x: 1100 }}
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />

      <Modal open={proofOpen} onCancel={() => setProofOpen(false)} footer={null} title="付款凭证" width={480}>
        {proofUrl && <Image src={proofUrl} alt="付款凭证" style={{ width: '100%' }} />}
      </Modal>
    </div>
  );
}

/**
 * 收款码管理。上传后启用即生效，用户下单时自动取 sort_order 最小的启用项。
 */
export function AdminQrcodesPane() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<QrcodeView[]>([]);
  const [loading, setLoading] = useState(false);
  const [previews, setPreviews] = useState<Record<number, string>>({});
  const [addOpen, setAddOpen] = useState(false);
  const [draft, setDraft] = useState<{ channel: string; label: string; accountNote: string; imageKey: string }>({
    channel: 'wechat',
    label: '',
    accountNote: '',
    imageKey: '',
  });
  const [uploading, setUploading] = useState(false);
  const [draftPreview, setDraftPreview] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await adminListQrcodes();
      setRows(list);
      // 逐个拉预览图（私有对象，需带 token）
      const map: Record<number, string> = {};
      await Promise.all(
        list.map(async (q) => {
          try {
            map[q.id] = await loadImageBlob(q.imagePath);
          } catch {
            /* 单张失败不影响其它 */
          }
        }),
      );
      setPreviews(map);
    } catch {
      message.error('加载收款码失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  const doUpload = async (file: File) => {
    setUploading(true);
    try {
      const key = await uploadProofImage(file);
      setDraft((d) => ({ ...d, imageKey: key }));
      setDraftPreview(URL.createObjectURL(file));
      message.success('图片已上传');
    } catch {
      message.error('上传失败');
    } finally {
      setUploading(false);
    }
    return false;
  };

  const save = async () => {
    if (!draft.imageKey) {
      message.warning('请先上传收款码图片');
      return;
    }
    try {
      await adminUpsertQrcode(draft);
      message.success('已保存');
      setAddOpen(false);
      setDraft({ channel: 'wechat', label: '', accountNote: '', imageKey: '' });
      setDraftPreview('');
      void load();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '保存失败');
    }
  };

  const toggle = async (q: QrcodeView, enabled: boolean) => {
    try {
      await adminUpsertQrcode({ id: q.id, enabled });
      void load();
    } catch {
      message.error('操作失败');
    }
  };

  const remove = async (q: QrcodeView) => {
    try {
      await adminDeleteQrcode(q.id);
      message.success('已删除');
      void load();
    } catch {
      message.error('删除失败');
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 14 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
          添加收款码
        </Button>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          刷新
        </Button>
      </Space>

      <div style={{ fontSize: 12, color: 'var(--pea-text-3, #888)', marginBottom: 14, lineHeight: 1.7 }}>
        用户下单时展示排序最靠前的<b>启用中</b>收款码。个人码无法自动确认到账，付款后需在「支付订单」页确认。
        接入微信支付商户号后，把 <code>PEA_PAY_PROVIDER</code> 改为 <code>wechat_native</code> 即自动开通，此处配置可保留备用。
      </div>

      {rows.length === 0 ? (
        <Card className="pea-card" style={{ textAlign: 'center', padding: 30 }}>
          <PictureOutlined style={{ fontSize: 30, color: '#ccc' }} />
          <div style={{ marginTop: 10, color: 'var(--pea-text-3, #888)' }}>
            还没有收款码。未配置时用户无法下单支付。
          </div>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
          {rows.map((q) => (
            <Card
              key={q.id}
              className="pea-card"
              styles={{ body: { padding: 14 } }}
              style={{ width: 220, opacity: q.enabled ? 1 : 0.55 }}
            >
              <div
                style={{
                  height: 180,
                  display: 'grid',
                  placeItems: 'center',
                  background: '#fff',
                  borderRadius: 10,
                  overflow: 'hidden',
                }}
              >
                {previews[q.id] ? (
                  <Image src={previews[q.id]} alt={q.label} style={{ maxHeight: 180 }} />
                ) : (
                  <PictureOutlined style={{ fontSize: 28, color: '#ddd' }} />
                )}
              </div>
              <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Tag color={q.channel === 'alipay' ? 'blue' : 'green'}>
                  {q.label || (q.channel === 'alipay' ? '支付宝' : '微信')}
                </Tag>
                <Space size={4}>
                  <Switch size="small" checked={q.enabled} onChange={(v) => toggle(q, v)} />
                  <Popconfirm title="删除该收款码？" onConfirm={() => remove(q)}>
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              </div>
              {q.accountNote && (
                <div style={{ fontSize: 12, color: 'var(--pea-text-3, #888)', marginTop: 4 }}>
                  {q.accountNote}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={addOpen}
        title="添加收款码"
        onCancel={() => setAddOpen(false)}
        onOk={save}
        okText="保存"
        width={420}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>收款渠道</div>
            <Select
              style={{ width: '100%' }}
              value={draft.channel}
              onChange={(v) => setDraft((d) => ({ ...d, channel: v }))}
              options={[
                { value: 'wechat', label: '微信' },
                { value: 'alipay', label: '支付宝' },
                { value: 'other', label: '其他' },
              ]}
            />
          </div>
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>展示名称</div>
            <Input
              placeholder="如：微信扫码"
              value={draft.label}
              onChange={(e) => setDraft((d) => ({ ...d, label: e.target.value }))}
            />
          </div>
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>收款人备注（选填）</div>
            <Input
              placeholder="用户付款时可见，便于核对"
              value={draft.accountNote}
              onChange={(e) => setDraft((d) => ({ ...d, accountNote: e.target.value }))}
            />
          </div>
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>二维码图片</div>
            <Upload accept="image/*" showUploadList={false} beforeUpload={(f) => doUpload(f as File)}>
              <Button icon={<PictureOutlined />} loading={uploading}>
                {draft.imageKey ? '重新选择' : '选择图片'}
              </Button>
            </Upload>
            {draftPreview && (
              <img
                src={draftPreview}
                alt="预览"
                style={{ display: 'block', marginTop: 10, maxWidth: 160, borderRadius: 8 }}
              />
            )}
          </div>
        </Space>
      </Modal>
    </div>
  );
}
