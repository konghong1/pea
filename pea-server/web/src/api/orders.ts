import { api, asArray } from './client';
import { syncBalance } from '../lib/balanceSync';

/* ═══════════════════════════ 类型 ═══════════════════════════ */

export type OrderStatus =
  | 'pending'
  | 'submitted'
  | 'paid'
  | 'rejected'
  | 'cancelled'
  | 'expired';

export interface OrderView {
  orderNo: string;
  planId: string;
  planName: string;
  planLevel: number;
  tapies: number;
  durationDays: number;
  /** 套餐标价（分） */
  amountCents: number;
  /** 实际应付（分）—— 含唯一识别尾数，付款必须一分不差 */
  payAmountCents: number;
  provider: string;
  status: OrderStatus;
  statusText: string;
  proofKey: string | null;
  proofNote: string | null;
  reviewNote: string | null;
  granted: boolean;
  expiresAt: string;
  createdAt: string;
  reviewedAt: string | null;
  userId?: number;
  userEmail?: string;
  userName?: string;
}

export interface PaymentIntent {
  provider: 'manual_qr' | 'wechat_native' | 'codepay';
  requiresProof: boolean;
  qrcode?: {
    id: number;
    channel: string;
    label: string;
    accountNote: string;
    /** manual_qr: 需带 token 拉取的图片接口路径，用 loadImageBlob() 转 blob URL */
    imagePath?: string;
    /** codepay: 网关返回的二维码图片直链（外部地址，直接 <img> 渲染） */
    imageUrl?: string;
    /** codepay: 网关返回的待编码支付链接，用 QRCode 渲染 */
    payUrl?: string;
  };
  /** wechat_native / codepay: 支付二维码链接，前端自行渲染二维码 */
  codeUrl?: string;
  hint?: string;
}

export interface CreateOrderResult {
  order: OrderView;
  intent: PaymentIntent;
}

export interface PaymentInfo {
  provider: 'manual_qr' | 'wechat_native';
  autoConfirm: boolean;
  requiresProof: boolean;
}

/* ═══════════════════════════ 用户侧 ═══════════════════════════ */

export async function getPaymentInfo(): Promise<PaymentInfo> {
  const { data } = await api.get('/orders/payment-info');
  return data;
}

/** 下单。同套餐存在未结束订单时后端会复用，不会重复生成金额尾数。 */
export async function createOrder(planId: string): Promise<CreateOrderResult> {
  const { data } = await api.post('/orders', { planId });
  return data;
}

export async function getOrder(orderNo: string): Promise<{ order: OrderView; intent?: PaymentIntent }> {
  const { data } = await api.get(`/orders/${orderNo}`);
  return data;
}

export async function listMyOrders(limit = 20): Promise<OrderView[]> {
  const { data } = await api.get('/orders', { params: { limit } });
  return asArray<OrderView>(data);
}

export async function submitProof(
  orderNo: string,
  payload: { proofKey?: string; proofNote?: string },
): Promise<OrderView> {
  const { data } = await api.post(`/orders/${orderNo}/proof`, payload);
  return data;
}

export async function cancelOrder(orderNo: string): Promise<OrderView> {
  const { data } = await api.post(`/orders/${orderNo}/cancel`);
  return data;
}

/** 上传付款截图，返回对象 key（复用通用文件上传通道）。 */
export async function uploadProofImage(file: File): Promise<string> {
  const form = new FormData();
  form.append('file', file);
  const { data } = await api.post('/files/upload', form);
  return data.key as string;
}

const imgCache = new Map<string, string>();

/** 收款码/凭证图片：<img src> 不带 Authorization，必须 blob 拉取。 */
export async function loadImageBlob(path: string): Promise<string> {
  if (imgCache.has(path)) return imgCache.get(path)!;
  const resp = await api.get(path, { responseType: 'blob' });
  const url = URL.createObjectURL(resp.data);
  imgCache.set(path, url);
  return url;
}

/* ═══════════════════════════ 管理员侧 ═══════════════════════════ */

export async function adminListOrders(status = 'all', limit = 50): Promise<OrderView[]> {
  const { data } = await api.get('/admin/orders', { params: { status, limit } });
  return asArray<OrderView>(data);
}

export async function adminPendingCount(): Promise<{ submitted: number; pending: number }> {
  const { data } = await api.get('/admin/orders/pending-count');
  return data;
}

/** 确认到账 → 立即发放权益。幂等，重复点击不会双发。 */
export async function adminApproveOrder(
  orderNo: string,
  payload: { reviewNote?: string; paidAmountCents?: number } = {},
): Promise<OrderView> {
  const { data } = await api.post(`/admin/orders/${orderNo}/approve`, payload);
  // 管理员给自己开通时余额会变，顺手同步一次
  syncBalance();
  return data;
}

export async function adminRejectOrder(orderNo: string, reviewNote?: string): Promise<OrderView> {
  const { data } = await api.post(`/admin/orders/${orderNo}/reject`, { reviewNote });
  return data;
}

export interface QrcodeView {
  id: number;
  channel: string;
  label: string;
  accountNote: string;
  imageKey: string;
  imagePath: string;
  enabled: boolean;
  sortOrder: number;
}

export async function adminListQrcodes(): Promise<QrcodeView[]> {
  const { data } = await api.get('/admin/payment-qrcodes');
  return data;
}

export async function adminUpsertQrcode(input: Partial<QrcodeView> & { imageKey?: string }) {
  const { data } = await api.post('/admin/payment-qrcodes', input);
  return data as QrcodeView;
}

export async function adminDeleteQrcode(id: number) {
  await api.delete(`/admin/payment-qrcodes/${id}`);
}

/** 分 → ¥ 展示（保留两位，尾数是对账识别码，不可省略）。 */
export function yuan(cents: number): string {
  return (cents / 100).toFixed(2);
}
