import { useCallback, useEffect, useRef, useState } from 'react';
import { App, Button, Card, Empty, Skeleton, Tag } from 'antd';
import { CheckCircleFilled } from '@ant-design/icons';
import { listPlans, purchasePlan, type PlanView } from '../../api/catalog';
import { useAuth } from '../../store/auth';
import { useUi } from '../../store/ui';

/**
 * 套餐购买页 (Phase 4)。
 *  - 购买是"到账 Tapies + 赋予权益等级 + 有效期"的原子事务 (服务端行锁 + 幂等)。
 *  - 前端为每次点击生成幂等键，避免网络重试/双击导致重复到账。
 *  - 购买成功后刷新余额 & 权益 (refreshMe)。
 */
export default function Plans() {
  const { message } = App.useApp();
  const { balance, planLevel, effectivePlanLevel, refreshMe } = useAuth();
  const setActive = useUi((s) => s.setActive);
  const [plans, setPlans] = useState<PlanView[]>([]);
  const [loading, setLoading] = useState(true);
  const [buyingId, setBuyingId] = useState<string | null>(null);
  // 每个套餐一次会话内的幂等键，重复点击复用同键 → 后端只发放一次
  const idemRef = useRef<Record<string, string>>({});

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

  useEffect(() => {
    void load();
    void refreshMe();
  }, [load, refreshMe]);

  const buy = async (p: PlanView) => {
    if (p.priceCents <= 0) {
      message.info('免费套餐无需购买，注册时已发放权益');
      return;
    }
    if (!idemRef.current[p.id]) {
      idemRef.current[p.id] = `${p.id}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
    setBuyingId(p.id);
    try {
      const res = await purchasePlan(p.id, idemRef.current[p.id]);
      if (res.duplicated) {
        message.info('该订单已处理，未重复扣费');
      } else {
        message.success(`购买成功，到账 ${res.tapiesGranted} Tapies`);
      }
      // 购买成功后允许后续再次购买（续费）：重置该套餐幂等键
      delete idemRef.current[p.id];
      await refreshMe();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '购买失败');
    } finally {
      setBuyingId(null);
    }
  };

  return (
    <div className="pea-page">
      <div className="pea-page-pad" style={{ maxWidth: 1120, margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>订阅套餐</h2>
            <p style={{ color: 'var(--pea-text-3, #888)' }}>
              购买后立即到账 Tapies 并解锁更高权益模型。当前余额 <b>💎 {balance}</b>
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
                    {free ? '免费权益（已发放）' : owned ? '续费 / 叠加' : '立即购买'}
                  </Button>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
