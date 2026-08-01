import { Injectable } from '@nestjs/common';
import axios from 'axios';
import { ConfigService } from '@nestjs/config';
import * as crypto from 'crypto';
import type { OrderContext, PaymentIntent, PaymentProvider } from './payment.types';

export interface CodepayConfig {
  gatewayUrl: string;
  pid: string;
  key: string;
  createPath: string;
  signAlgo: 'md5' | 'hmac-md5';
  signStyle: 'direct' | 'saltparam';
  signField: string;
  fieldOrder: string;
  fieldMoney: string;
  fieldTradeNo: string;
  reqPid: string;
  reqOutTradeNo: string;
  reqName: string;
  reqMoney: string;
  reqNotify: string;
  reqReturn: string;
  reqTypeField: string;
  reqTypeValue: string;
  signTypeField: string;
  signTypeValue: string;
  respQr: string;
  respPayUrl: string;
  moneyUnit: 'yuan' | 'cent';
  publicBaseUrl: string;
}

/**
 * 通用码支付 / 聚合支付网关（默认按易支付 Epay 协议实现）。
 *
 * 为什么需要它：个人收款码（微信/支付宝个人码）本身**没有服务器回调**，
 * 微信只给收款人自己推一条到账通知，服务器无法知道「谁付了、付了多少」。
 * 码支付服务商（码支付 / 易支付 / 聚合支付类）是折中方案：
 *   它把你的**个人**码包一层，用户扫的是它的码 → 它收到款 → 回调你的 /pay/notify/codepay
 *   → 你按签名验真后自动 confirmPaid → 发放权益。**全程零人工**，且个人即可接入，无需营业执照。
 *
 * 各家字段名 / 签名算法 / 回调格式差异很大，因此这里**全部走环境变量**，未定服务商也能先编译部署，
 * 选定后只填配置、不改代码。默认取值覆盖绝大多数 Epay 兼容服务。
 */
@Injectable()
export class CodepayProvider implements PaymentProvider {
  readonly name = 'codepay' as const;
  /** 码支付有回调，具备自动确认能力。 */
  readonly autoConfirm = true;

  constructor(private readonly config: ConfigService) {}

  private cfg(): CodepayConfig {
    const p = this.config.get('payment.codepay') as CodepayConfig;
    return p;
  }

  /** 网关地址 / 商户号 / 通信密钥三者齐备才算已配置，否则下单时给出清晰报错。 */
  isConfigured(): boolean {
    const c = this.cfg();
    return !!(c.gatewayUrl && c.pid && c.key);
  }

  /**
   * 计算签名（Epay 风格，可配置）。
   * 参与签名的字段 = 除 sign 外的所有字段，按 key 升序拼接为 querystring，
   * 再按 signStyle 追加通信密钥（direct: 直接拼接；saltparam: &salt=密钥），
   * 最后取 MD5 / HMAC-MD5。
   * 绝大多数 Epay 兼容服务默认配置即可；个别服务需要仅对子集签名时，在此函数扩展即可。
   */
  private sign(params: Record<string, any>): string {
    const c = this.cfg();
    const keys = Object.keys(params)
      .filter((k) => k !== c.signField)
      .sort();
    const raw =
      keys.map((k) => `${k}=${params[k]}`).join('&') +
      (c.signStyle === 'saltparam' ? `&salt=${c.key}` : c.key);
    if (c.signAlgo === 'hmac-md5') {
      return crypto.createHmac('md5', c.key).update(raw).digest('hex');
    }
    return crypto.createHash('md5').update(raw).digest('hex');
  }

  /** 下单：调网关创建订单，取回支付二维码（图片直链或待编码链接）。 */
  async createIntent(ctx: OrderContext): Promise<PaymentIntent> {
    const c = this.cfg();
    if (!this.isConfigured()) {
      throw new Error(
        '码支付未配置：请设置 PEA_CODEPAY_GATEWAY_URL / PEA_CODEPAY_PID / PEA_CODEPAY_KEY',
      );
    }
    const notifyUrl = `${c.publicBaseUrl.replace(/\/$/, '')}/pay/notify/codepay`;
    const moneyYuan = (ctx.payAmountCents / 100).toFixed(2);

    // 下单请求参数（字段名可配）。sign_type 随请求带但不参与签名。
    const params: Record<string, any> = {
      [c.reqPid]: c.pid,
      [c.reqOutTradeNo]: ctx.orderNo,
      [c.reqName]: `pea-${ctx.planId}`,
      [c.reqMoney]: moneyYuan,
      [c.reqNotify]: notifyUrl,
      [c.reqReturn]: notifyUrl,
      [c.reqTypeField]: c.reqTypeValue,
      [c.signTypeField]: c.signTypeValue,
    };
    params[c.signField] = this.sign(params);

    const base = c.gatewayUrl.replace(/\/$/, '');
    const url = `${base}${c.createPath}`;
    const resp = await axios.post(url, new URLSearchParams(params).toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      timeout: 8000,
    });
    const data = resp.data && typeof resp.data === 'object' ? resp.data : {};
    const qrImage = data?.[c.respQr];
    const payUrl = data?.[c.respPayUrl];
    if (!qrImage && !payUrl) {
      throw new Error(
        '码支付网关未返回二维码，请检查 PEA_CODEPAY_RESP_QR / PEA_CODEPAY_RESP_PAY_URL 与网关实际返回字段',
      );
    }
    return {
      provider: 'codepay',
      requiresProof: false,
      qrcode: {
        id: 0,
        channel: 'codepay',
        label: '扫码支付',
        accountNote: '',
        imagePath: undefined,
        imageUrl: qrImage || undefined,
        payUrl: payUrl || undefined,
      },
    };
  }

  /**
   * 校验回调签名并解出订单号/金额/交易号。
   * 返回 null 表示签名不通过或必要字段缺失（应判为伪造 / 非法请求）。
   * 注意：签约字段集合与拼接风格由 sign() 配置决定，与下单保持一致。
   */
  verifyNotify(body: Record<string, any>): {
    orderNo: string;
    paidAmountCents: number;
    tradeNo: string;
  } | null {
    if (!body || typeof body !== 'object') return null;
    const c = this.cfg();
    const sign = body[c.signField];
    if (!sign) return null;
    const expected = this.sign(body);
    if (expected.toLowerCase() !== String(sign).toLowerCase()) return null;

    const orderNo = body[c.fieldOrder];
    const moneyRaw = body[c.fieldMoney];
    if (!orderNo || moneyRaw === undefined || moneyRaw === '') return null;
    const moneyNum = Number(moneyRaw);
    if (!Number.isFinite(moneyNum) || moneyNum <= 0) return null;
    const paidAmountCents = c.moneyUnit === 'cent' ? Math.round(moneyNum) : Math.round(moneyNum * 100);
    return {
      orderNo: String(orderNo),
      paidAmountCents,
      tradeNo: body[c.fieldTradeNo] ? String(body[c.fieldTradeNo]) : '',
    };
  }
}
