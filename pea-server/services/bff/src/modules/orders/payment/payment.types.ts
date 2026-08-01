/**
 * 支付通道抽象。
 *
 * 引入这层的唯一目的：让「个人收款码 + 人工确认」与「微信商户号 + 回调自动开通」
 * 走完全相同的订单状态机，切换时只改一个环境变量，不动业务代码、不迁移数据。
 *
 *   下单 createIntent() ──► 用户付款 ──► 确认到账 ──► PlansService.grantEntitlement()
 *                                          ▲
 *                     manual_qr: 管理员点「确认到账」
 *                     wechat_native: 支付回调自动触发
 *
 * 差异只有一处：谁来触发「确认到账」。其余全部一致。
 */

export type PaymentProviderName = 'manual_qr' | 'wechat_native' | 'codepay';

/** 下单后返回给前端、用于渲染支付弹窗的数据。 */
export interface PaymentIntent {
  provider: PaymentProviderName;
  /** 用户是否需要手动上传付款凭证（manual_qr = true，网关回调路径 = false）。 */
  requiresProof: boolean;
  /** manual_qr: 后台配置的收款码；codepay: 网关返回的支付二维码。 */
  qrcode?: {
    id: number;
    channel: string;
    label: string;
    accountNote: string;
    /**
     * BFF 代理的图片接口路径（manual_qr 用）。需带 Authorization 头访问，
     * 前端用 blob 方式拉取（<img src> 不会携带 token）。codepay 不走此字段。
     */
    imagePath?: string;
    /**
     * codepay: 网关返回的二维码图片直链（外部地址，前端直接 <img> 渲染，无需 token）。
     */
    imageUrl?: string;
    /**
     * codepay: 网关返回的待编码支付链接（weixin:// 或 https://），前端用 QRCode 渲染。
     * 与 imageUrl 二选一。
     */
    payUrl?: string;
  };
  /** wechat_native / codepay: 支付二维码链接，前端自行渲染二维码。 */
  codeUrl?: string;
  /** 给用户看的付款提示文案。 */
  hint?: string;
}

/** 创建支付意图时传入的订单上下文（只读快照）。 */
export interface OrderContext {
  orderNo: string;
  userId: number;
  planId: string;
  planName: string;
  /** 实际应付金额（分），已含随机尾数。 */
  payAmountCents: number;
  expiresAt: Date;
}

export interface PaymentProvider {
  readonly name: PaymentProviderName;
  /** 是否具备自动确认能力（有回调）。false 表示必须人工确认到账。 */
  readonly autoConfirm: boolean;
  /** 下单后调用，产出前端渲染支付界面所需的数据。 */
  createIntent(ctx: OrderContext): Promise<PaymentIntent>;
}
