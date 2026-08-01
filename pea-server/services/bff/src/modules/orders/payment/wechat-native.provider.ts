import { Injectable, BadRequestException, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as crypto from 'crypto';
import type {
  OrderContext,
  PaymentIntent,
  PaymentProvider,
  PaymentProviderName,
} from './payment.types';

const WXPAY_NATIVE_API = 'https://api.mch.weixin.qq.com/v3/pay/transactions/native';

/** 微信支付 APIv3 回调解密后的报文（只取我们关心的字段）。 */
export interface WechatNotifyPayload {
  out_trade_no: string;
  transaction_id: string;
  trade_state: string;
  amount?: { total?: number; payer_total?: number };
  success_time?: string;
}

/**
 * 微信支付 Native 扫码通道（需商户号）。
 *
 * 与 manual_qr 的唯一差别是「谁触发确认到账」：这里由微信回调触发，全自动。
 * 订单表、状态机、发放函数完全复用。
 *
 * 启用步骤（拿到商户号后）：
 *   1. 填环境变量 PEA_WXPAY_APPID / MCHID / API_V3_KEY / SERIAL_NO / PRIVATE_KEY / NOTIFY_URL
 *   2. 把 PEA_PAY_PROVIDER 改成 wechat_native
 *   3. 重启 bff。无需改代码、无需迁移数据、历史订单不受影响。
 *
 * ⚠️ 安全说明：回调采用 APIv3 的 AES-256-GCM 解密。GCM 自带认证标签，
 *    能解密成功即证明报文由持有 apiV3Key 的一方（微信）产生，可防伪造与篡改。
 *    若需更严格的合规要求，可再补微信平台证书的 RSA 应答签名验证。
 */
@Injectable()
export class WechatNativeProvider implements PaymentProvider {
  readonly name: PaymentProviderName = 'wechat_native';
  readonly autoConfirm = true;

  private readonly logger = new Logger(WechatNativeProvider.name);

  constructor(private readonly config: ConfigService) {}

  private cfg() {
    return this.config.get('payment').wechat as {
      appId: string;
      mchId: string;
      apiV3Key: string;
      serialNo: string;
      privateKey: string;
      notifyUrl: string;
    };
  }

  /** 商户参数是否齐备。缺任意一项都无法下单，提前给出可读报错而不是让微信返回 401。 */
  isConfigured(): boolean {
    const c = this.cfg();
    return !!(c.appId && c.mchId && c.apiV3Key && c.serialNo && c.privateKey && c.notifyUrl);
  }

  /**
   * APIv3 请求签名。签名串格式（每行以 \n 结尾，包括最后一行）：
   *   HTTP方法\nURL路径\n时间戳\n随机串\n请求报文主体\n
   */
  private buildAuthorization(method: string, urlPath: string, body: string): string {
    const c = this.cfg();
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const nonceStr = crypto.randomBytes(16).toString('hex').toUpperCase();
    const message = `${method}\n${urlPath}\n${timestamp}\n${nonceStr}\n${body}\n`;
    // 私钥支持 \n 转义形式（方便放进单行环境变量）
    const pem = c.privateKey.includes('\\n') ? c.privateKey.replace(/\\n/g, '\n') : c.privateKey;
    const signature = crypto.createSign('RSA-SHA256').update(message).sign(pem, 'base64');
    return (
      `WECHATPAY2-SHA256-RSA2048 mchid="${c.mchId}",` +
      `nonce_str="${nonceStr}",signature="${signature}",` +
      `timestamp="${timestamp}",serial_no="${c.serialNo}"`
    );
  }

  async createIntent(ctx: OrderContext): Promise<PaymentIntent> {
    if (!this.isConfigured()) {
      throw new BadRequestException(
        '微信支付商户参数未配置完整，暂时无法使用扫码支付。请联系管理员，或改用收款码通道。',
      );
    }
    const c = this.cfg();
    const payload = {
      appid: c.appId,
      mchid: c.mchId,
      description: `${ctx.planName}`.slice(0, 127),
      out_trade_no: ctx.orderNo,
      notify_url: c.notifyUrl,
      time_expire: new Date(ctx.expiresAt).toISOString().replace('Z', '+00:00'),
      amount: { total: ctx.payAmountCents, currency: 'CNY' },
    };
    const body = JSON.stringify(payload);
    const auth = this.buildAuthorization('POST', '/v3/pay/transactions/native', body);

    const res = await fetch(WXPAY_NATIVE_API, {
      method: 'POST',
      headers: {
        Authorization: auth,
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'User-Agent': 'pea-bff/1.0',
      },
      body,
    });
    const text = await res.text();
    if (!res.ok) {
      this.logger.error(`wxpay native order failed ${res.status}: ${text}`);
      throw new BadRequestException('微信支付下单失败，请稍后重试或改用收款码通道。');
    }
    const data = JSON.parse(text) as { code_url?: string };
    if (!data.code_url) {
      throw new BadRequestException('微信支付未返回二维码链接。');
    }
    return {
      provider: this.name,
      requiresProof: false,
      codeUrl: data.code_url,
      hint: '请使用微信扫码完成支付，到账后权益将自动开通。',
    };
  }

  /**
   * 解密回调报文。resource 为微信 APIv3 的加密体。
   * 解密失败即视为伪造请求（GCM 认证标签校验不通过），调用方应返回 401。
   */
  decryptNotify(resource: {
    ciphertext: string;
    nonce: string;
    associated_data?: string;
  }): WechatNotifyPayload {
    const key = Buffer.from(this.cfg().apiV3Key, 'utf8');
    if (key.length !== 32) {
      throw new BadRequestException('apiV3Key 必须为 32 字节');
    }
    const cipherBuf = Buffer.from(resource.ciphertext, 'base64');
    // 末 16 字节为 GCM 认证标签
    const authTag = cipherBuf.subarray(cipherBuf.length - 16);
    const data = cipherBuf.subarray(0, cipherBuf.length - 16);
    const decipher = crypto.createDecipheriv(
      'aes-256-gcm',
      key,
      Buffer.from(resource.nonce, 'utf8'),
    );
    decipher.setAuthTag(authTag);
    if (resource.associated_data) {
      decipher.setAAD(Buffer.from(resource.associated_data, 'utf8'));
    }
    const plain = Buffer.concat([decipher.update(data), decipher.final()]).toString('utf8');
    return JSON.parse(plain) as WechatNotifyPayload;
  }
}
