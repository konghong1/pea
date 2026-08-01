import { useCallback, useEffect, useState } from 'react';
import { App, Button, Card, Empty, Skeleton, Table, Tag } from 'antd';
import { CheckCircleFilled } from '@ant-design/icons';
import { listPlans, type PlanView } from '../../api/catalog';
import {
  createOrder,
  listMyOrders,
  yuan,
  type OrderView,
  type PaymentIntent,
} from '../../api/orders';
import { useAuth } from '../../store/auth';
import { useUi } from '../../store/ui';
import PayModal from '../PayModal';

const STATUS_COLOR: Record<string, string> = {
  pending: 'gold',
  submitted: 'processing',
  paid: 'success',
  rejected: 'error',
  cancelled: 'default',
  expired: 'default',
};

/**
 * 套餐购买页。
 *
 * ⚠️ 支付边界（2026-08 改造）：
 *   这里不再直接调用 /plans/purchase 到账 —— 那条路径没有任何支付校验，
 *   任何登录用户都能无限调用给自己续费。现在统一走订单：
 *     下单 → 扫收款码付款 → 确认到账 → 发放权益
 *   前端只负责下单与展示，权益发放完全由服务端在确认收款后触发。
 */
export default function Plans() {
  const { message } = App.useApp();
  const { balance, planLevel, effectivePlanLevel, refreshMe } = useAuth();
  const setActive = useUi((s) => s.setActive);
  const [plans, setPlans] = useState<PlanView[]>([]);
  const [orders, setOrders] = useState<OrderView[]>([]);
  const [loading, setLoading] = useState(true);
  const [buyingId, setBuyingId] = useState<string | null>(null);

  const [payOpen, setPayOpen] = useState(false);
  const [payOrder, setPayOrder] = useState<OrderView | null>(null);
  const [payIntent, setPayIntent] = useState<PaymentIntent | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPlans(await listPlans());
    } catch {
      message.error('加载套餐失败');
    } finally {
      setLoading(false);
    }
  }, [message]);

  const loadOrders = useCallback(async () => {
    try {
      setOrders(await listMyOrders(20));
    } catch {
      /* 订单列表失败不阻断套餐展示 */
    }
  }, []);

  useEffect(() => {
    void load();
    void loadOrders();
    void refreshMe();
  }, [load, loadOrders, refreshMe]);

  const buy = async (p: PlanView) => {
    if (p.priceCents <= 0) {
      message.info('免费套餐无需购买，注册时已发放权益');
      return;
    }
    setBuyingId(p.id);
    try {
      const { order, intent } = await createOrder(p.id);
      setPayOrder(order);
      setPayIntent(intent);
      setPayOpen(true);
      void loadOrders();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '下单失败');
    } finally {
      setBuyingId(null);
    }
  };

  /** 从订单列表继续未完成的支付 */
  const resume = async (o: OrderView) => {
    try {
      const { getOrder } = await import('../../api/orders');
      const { order, intent } = await getOrder(o.orderNo);
      setPayOrder(order);
      setPayIntent(intent ?? null);
      setPayOpen(true);
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '打开订单失败');
    }
  };

  return (
    <div className="pea-page">
      <div className="pea-page-pad" style={{ maxWidth: 1120, margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>订阅套餐</h2>
            <p style={{ color: 'var(--pea-text-3, #888)' }}>
              扫码付款并确认到账后，Tapies 立即入账并解锁更高权益模型。当前余额 <b>💎 {balance}</b>
              {planLevel > 0 && (
                <>
                  {' '}· 当前权益 <Tag color={effectivePlanLevel > 0 ? 'purple' : 'default'}>Lv.{effectivePlanLevel}</Tag>
                  {effectivePlanLevel === 0 && planLevel > 0 && <span style={{ color: '#e03131' }}>（已过期）</span>}
                </>
              )}
            </p>
          </div>
          <Button onClick={() => setActive('workspace')}>返回工作空间</Button>
        </div>

        {loading ? (
          <div className="pea-card-grid" style={{ marginTop: 24 }}>
            {[0, 1, 2].map((i) => (
              <Card key={i} className="pea-card">
                <Skeleton active />
              </Card>
            ))}
          </div>
        ) : plans.length === 0 ? (
          <Empty description="暂无可售套餐" style={{ marginTop: 60 }} />
        ) : (
          <div className="pea-card-grid" style={{ marginTop: 24 }}>
            {plans.map((p) => {
              const free = p.priceCents <= 0;
              const owned = effectivePlanLevel >= p.planLevel && p.planLevel > 0;
              return (
                <Card
                  key={p.id}
                  className="pea-card"
                  styles={{ body: { padding: 22, display: 'flex', flexDirection: 'column', minHeight: 300 } }}
                  style={{ borderColor: owned ? 'var(--pea-brand)' : undefined }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 18, fontWeight: 700 }}>{p.name}</span>
                    {owned && <Tag color="purple">已拥有</Tag>}
                  </div>
                  <div style={{ margin: '14px 0 6px' }}>
                    {free ? (
                      <span style={{ fontSize: 28, fontWeight: 800 }}>免费</span>
                    ) : (
                      <>
                        <span style={{ fontSize: 28, fontWeight: 800 }}>¥{(p.priceCents / 100).toFixed(0)}</span>
                        <span style={{ color: '#999', marginLeft: 6 }}>
                          / {p.durationDays > 0 ? `${p.durationDays}天` : '永久'}
                        </span>
                      </>
                    )}
                  </div>
                  <div style={{ color: 'var(--pea-brand)', fontWeight: 600, marginBottom: 14 }}>
                    💎 赠送 {p.tapies} Tapies
                  </div>
                  <div style={{ flex: 1 }}>
                    {(p.features ?? []).map((f) => (
                      <div key={f} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, fontSize: 13 }}>
                        <CheckCircleFilled style={{ color: 'var(--pea-brand)' }} />
                        <span>{f}</span>
                      </div>
                    ))}
                  </div>
                  <Button
                    type={free ? 'default' : 'primary'}
                    block
                    size="large"
                    disabled={free}
                    loading={buyingId === p.id}
                    onClick={() => buy(p)}
                    style={{ marginTop: 12 }}
                  >
                    {free ? '免费权益（已发放）' : owned ? '续费 / 升级' : '立即购买'}
                  </Button>
                </Card>
              );
            })}
          </div>
        )}

        {orders.length > 0 && (
          <Card
            className="pea-card"
            title="我的订单"
            style={{ marginTop: 28 }}
            styles={{ body: { padding: 0 } }}
          >
            <Table<OrderView>
              rowKey="orderNo"
              size="small"
              pagination={false}
              dataSource={orders}
              columns={[
                {
                  title: '订单号',
                  dataIndex: 'orderNo',
                  render: (v: string) => (
                    <span style={{ fontFamily: 'var(--pea-font-mono, monospace)', fontSize: 12 }}>{v}</span>
                  ),
                },
                { title: '套餐', dataIndex: 'planName', width: 120 },
                {
                  title: '应付',
                  dataIndex: 'payAmountCents',
                  width: 100,
                  render: (v: number) => `¥${yuan(v)}`,
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 110,
                  render: (v: string, r) => <Tag color={STATUS_COLOR[v] ?? 'default'}>{r.statusText}</Tag>,
                },
                {
                  title: '时间',
                  dataIndex: 'createdAt',
                  width: 160,
                  render: (v: string) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-'),
                },
                {
                  title: '',
                  width: 90,
                  render: (_: unknown, r) =>
                    r.status === 'pending' || r.status === 'submitted' ? (
                      <Button type="link" size="small" onClick={() => resume(r)}>
                        去支付
                      </Button>
                    ) : null,
                },
              ]}
            />
          </Card>
        )}
      </div>

      <PayModal
        open={payOpen}
        order={payOrder}
        intent={payIntent}
        onClose={() => {
          setPayOpen(false);
          void loadOrders();
        }}
        onPaid={() => {
          void loadOrders();
          void load();
        }}
      />
    </div>
  );
}
