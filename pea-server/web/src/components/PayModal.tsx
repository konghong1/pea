import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Input, Modal, QRCode, Result, Spin, Steps, Tag, Upload } from 'antd';
import {
  CheckCircleFilled,
  CopyOutlined,
  PictureOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  cancelOrder,
  getOrder,
  loadImageBlob,
  submitProof,
  uploadProofImage,
  yuan,
  type OrderView,
  type PaymentIntent,
} from '../api/orders';
import { useAuth } from '../store/auth';

/** 订单未结束时的状态轮询间隔。管理员在后台确认后，用户这边最多 4s 感知到。 */
const POLL_MS = 4000;

interface Props {
  open: boolean;
  order: OrderView | null;
  intent: PaymentIntent | null;
  onClose: () => void;
  /** 权益开通成功回调（用于外层刷新套餐卡片状态） */
  onPaid?: () => void;
}

/**
 * 支付弹窗。
 *
 * 两种通道共用同一套 UI 骨架，差异只体现在中间的付款区：
 *   - manual_qr    展示后台配置的个人收款码 + 上传付款凭证
 *   - wechat_native 展示微信返回的 code_url 二维码，无需上传凭证
 *
 * 无论哪种通道，右侧状态机与轮询逻辑完全一致，到账后自动跳成功态。
 */
export default function PayModal({ open, order, intent, onClose, onPaid }: Props) {
  const { message } = App.useApp();
  const refreshMe = useAuth((s) => s.refreshMe);
  const [cur, setCur] = useState<OrderView | null>(order);
  const [qrUrl, setQrUrl] = useState<string>('');
  const [qrLoading, setQrLoading] = useState(false);
  const [proofKey, setProofKey] = useState<string>('');
  const [proofName, setProofName] = useState<string>('');
  const [note, setNote] = useState('');
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [now, setNow] = useState(Date.now());
  const paidHandled = useRef(false);

  useEffect(() => {
    setCur(order);
    paidHandled.current = false;
    setProofKey('');
    setProofName('');
    setNote('');
  }, [order?.orderNo]);

  // 收款码图片：私有对象，必须带 token 走 blob
  useEffect(() => {
    const path = intent?.qrcode?.imagePath;
    if (!open || !path) {
      setQrUrl('');
      return;
    }
    let alive = true;
    setQrLoading(true);
    loadImageBlob(path)
      .then((u) => alive && setQrUrl(u))
      .catch(() => alive && setQrUrl(''))
      .finally(() => alive && setQrLoading(false));
    return () => {
      alive = false;
    };
  }, [open, intent?.qrcode?.imagePath]);

  const finished = useMemo(
    () => !!cur && ['paid', 'rejected', 'cancelled', 'expired'].includes(cur.status),
    [cur],
  );

  // 状态轮询：订单未结束时持续拉取，管理员确认后自动跳成功态
  useEffect(() => {
    if (!open || !cur || finished) return;
    const timer = window.setInterval(async () => {
      try {
        const { order: fresh } = await getOrder(cur.orderNo);
        setCur(fresh);
      } catch {
        /* 网络抖动忽略，下一轮重试 */
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [open, cur?.orderNo, finished]);

  // 倒计时刷新
  useEffect(() => {
    if (!open || finished) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [open, finished]);

  // 到账后：刷新余额与权益，通知外层
  useEffect(() => {
    if (cur?.status === 'paid' && !paidHandled.current) {
      paidHandled.current = true;
      void refreshMe();
      onPaid?.();
    }
  }, [cur?.status, refreshMe, onPaid]);

  const remainMs = cur ? new Date(cur.expiresAt).getTime() - now : 0;
  const remainText = useMemo(() => {
    if (remainMs <= 0) return '已超时';
    const m = Math.floor(remainMs / 60000);
    const s = Math.floor((remainMs % 60000) / 1000);
    return `${m}:${String(s).padStart(2, '0')}`;
  }, [remainMs]);

  const step = useMemo(() => {
    if (!cur) return 0;
    if (cur.status === 'paid') return 2;
    if (cur.status === 'submitted') return 1;
    return 0;
  }, [cur]);

  const copyAmount = useCallback(() => {
    if (!cur) return;
    void navigator.clipboard?.writeText(yuan(cur.payAmountCents));
    message.success('金额已复制');
  }, [cur, message]);

  const doUpload = useCallback(
    async (file: File) => {
      setUploading(true);
      try {
        const key = await uploadProofImage(file);
        setProofKey(key);
        setProofName(file.name);
        message.success('凭证已上传');
      } catch {
        message.error('上传失败，请重试');
      } finally {
        setUploading(false);
      }
      return false;
    },
    [message],
  );

  const doSubmit = useCallback(async () => {
    if (!cur) return;
    if (!proofKey && !note.trim()) {
      message.warning('请上传付款截图，或填写付款备注');
      return;
    }
    setSubmitting(true);
    try {
      const updated = await submitProof(cur.orderNo, {
        proofKey: proofKey || undefined,
        proofNote: note.trim() || undefined,
      });
      setCur(updated);
      message.success('已提交，正在等待确认到账');
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '提交失败');
    } finally {
      setSubmitting(false);
    }
  }, [cur, proofKey, note, message]);

  const doCancel = useCallback(async () => {
    if (!cur) return;
    try {
      await cancelOrder(cur.orderNo);
      message.info('订单已取消');
      onClose();
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '取消失败');
    }
  }, [cur, message, onClose]);

  if (!cur) return null;

  const amountStr = yuan(cur.payAmountCents);
  const [intPart, decPart] = amountStr.split('.');

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
      centered
      destroyOnClose
      title={cur.status === 'paid' ? '开通成功' : `支付订单 · ${cur.planName}`}
    >
      {cur.status === 'paid' ? (
        <Result
          status="success"
          title={`${cur.planName} 已开通`}
          subTitle={
            <span>
              到账 <b>💎 {cur.tapies} Tapies</b>
              {cur.durationDays > 0 && ` · 有效期 ${cur.durationDays} 天`}
            </span>
          }
          extra={
            <Button type="primary" onClick={onClose}>
              开始创作
            </Button>
          }
        />
      ) : cur.status === 'rejected' || cur.status === 'cancelled' || cur.status === 'expired' ? (
        <Result
          status={cur.status === 'rejected' ? 'error' : 'warning'}
          title={cur.statusText}
          subTitle={cur.reviewNote || (cur.status === 'expired' ? '订单已超时，请重新下单' : '')}
          extra={<Button onClick={onClose}>关闭</Button>}
        />
      ) : (
        <div style={{ paddingTop: 4 }}>
          <Steps
            size="small"
            current={step}
            items={[{ title: '扫码付款' }, { title: '等待确认' }, { title: '权益开通' }]}
            style={{ marginBottom: 20 }}
          />

          {/* 应付金额：尾数是本单的对账识别码，必须一分不差 */}
          <div
            style={{
              background: 'var(--pea-surface-2, rgba(127,119,221,0.06))',
              border: '1px solid var(--pea-border, rgba(127,119,221,0.18))',
              borderRadius: 14,
              padding: '16px 18px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <div>
              <div style={{ fontSize: 12, color: 'var(--pea-text-3, #888)', marginBottom: 2 }}>
                应付金额
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
                <span style={{ fontSize: 18, fontWeight: 600 }}>¥</span>
                <span style={{ fontSize: 30, fontWeight: 700, letterSpacing: -0.5 }}>{intPart}</span>
                <span style={{ fontSize: 30, fontWeight: 700 }}>.</span>
                <span
                  style={{
                    fontSize: 30,
                    fontWeight: 700,
                    color: 'var(--pea-brand, #7f77dd)',
                    textDecoration: 'underline',
                    textDecorationStyle: 'dotted',
                    textUnderlineOffset: 5,
                  }}
                  title="金额尾数是本订单的识别码，请勿改动"
                >
                  {decPart}
                </span>
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <Button size="small" icon={<CopyOutlined />} onClick={copyAmount}>
                复制
              </Button>
              <div style={{ fontSize: 12, color: '#e8873a', marginTop: 8 }}>剩余 {remainText}</div>
            </div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--pea-text-3, #888)', margin: '8px 2px 16px' }}>
            金额尾数 <b style={{ color: 'var(--pea-brand, #7f77dd)' }}>.{decPart}</b>{' '}
            是本单的识别码，请按原额付款，便于快速核对到账。
          </div>

          {/* 付款区：三种通道各自渲染 */}
          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            {intent?.provider === 'wechat_native' && intent.codeUrl ? (
              <>
                <QRCode value={intent.codeUrl} size={180} bordered={false} />
                <div style={{ fontSize: 13, color: 'var(--pea-text-3, #888)', marginTop: 6 }}>
                  微信扫一扫完成支付，到账后自动开通
                </div>
              </>
            ) : intent?.provider === 'codepay' && intent.qrcode?.imageUrl ? (
              <>
                <img
                  src={intent.qrcode.imageUrl}
                  alt="收款码"
                  style={{
                    width: 200,
                    height: 200,
                    objectFit: 'contain',
                    borderRadius: 12,
                    border: '1px solid var(--pea-border, rgba(0,0,0,0.08))',
                    background: '#fff',
                    padding: 6,
                  }}
                />
                <div style={{ marginTop: 8 }}>
                  <Tag color="green">{intent.qrcode.label || '扫码支付'}</Tag>
                  <span style={{ fontSize: 12, color: 'var(--pea-text-3, #888)', marginLeft: 6 }}>
                    付款后自动开通，无需上传凭证
                  </span>
                </div>
              </>
            ) : intent?.provider === 'codepay' && intent.qrcode?.payUrl ? (
              <>
                <QRCode value={intent.qrcode.payUrl} size={180} bordered={false} />
                <div style={{ fontSize: 13, color: 'var(--pea-text-3, #888)', marginTop: 6 }}>
                  扫码支付，到账后自动开通
                </div>
              </>
            ) : qrLoading ? (
              <div style={{ height: 200, display: 'grid', placeItems: 'center' }}>
                <Spin />
              </div>
            ) : qrUrl ? (
              <>
                <img
                  src={qrUrl}
                  alt="收款码"
                  style={{
                    width: 200,
                    height: 200,
                    objectFit: 'contain',
                    borderRadius: 12,
                    border: '1px solid var(--pea-border, rgba(0,0,0,0.08))',
                    background: '#fff',
                    padding: 6,
                  }}
                />
                <div style={{ marginTop: 8 }}>
                  <Tag color={intent?.qrcode?.channel === 'alipay' ? 'blue' : 'green'}>
                    {intent?.qrcode?.label || '扫码付款'}
                  </Tag>
                  {intent?.qrcode?.accountNote && (
                    <span style={{ fontSize: 12, color: 'var(--pea-text-3, #888)', marginLeft: 6 }}>
                      {intent.qrcode.accountNote}
                    </span>
                  )}
                </div>
              </>
            ) : (
              <div style={{ padding: 20, color: '#e03131', fontSize: 13 }}>
                收款码未配置，请联系管理员
              </div>
            )}
          </div>

          {/* 凭证提交（仅人工确认通道需要） */}
          {intent?.requiresProof !== false && (
            <div style={{ borderTop: '1px solid var(--pea-border, rgba(0,0,0,0.06))', paddingTop: 14 }}>
              {cur.status === 'submitted' ? (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    background: 'rgba(250,199,117,0.14)',
                    border: '1px solid rgba(239,159,39,0.35)',
                    borderRadius: 12,
                    padding: '12px 14px',
                  }}
                >
                  <Spin size="small" />
                  <div style={{ fontSize: 13, lineHeight: 1.6 }}>
                    <b>已收到你的付款凭证</b>
                    <div style={{ color: 'var(--pea-text-3, #888)' }}>
                      到账核对通过后权益立即开通，本页会自动刷新，无需重复提交。
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                    付款后提交凭证
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    <Upload
                      accept="image/*"
                      showUploadList={false}
                      beforeUpload={(f) => doUpload(f as File)}
                    >
                      <Button icon={<PictureOutlined />} loading={uploading}>
                        {proofKey ? '重新选择' : '上传付款截图'}
                      </Button>
                    </Upload>
                    {proofKey && (
                      <span
                        style={{
                          fontSize: 12,
                          color: '#1d9e75',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          maxWidth: 220,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        <CheckCircleFilled /> {proofName}
                      </span>
                    )}
                  </div>
                  <Input
                    placeholder="付款备注（选填）：付款人昵称 / 转账单号后四位"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    maxLength={100}
                  />
                  <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
                    <Button
                      type="primary"
                      block
                      size="large"
                      loading={submitting}
                      onClick={doSubmit}
                    >
                      我已付款，提交凭证
                    </Button>
                    <Button size="large" onClick={doCancel}>
                      取消订单
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginTop: 14,
              fontSize: 12,
              color: 'var(--pea-text-3, #999)',
            }}
          >
            <span>订单号 {cur.orderNo}</span>
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              onClick={async () => {
                const { order: fresh } = await getOrder(cur.orderNo);
                setCur(fresh);
              }}
            >
              刷新状态
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
