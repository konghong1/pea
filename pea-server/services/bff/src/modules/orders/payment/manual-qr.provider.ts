import { Injectable, BadRequestException } from '@nestjs/common';
import { DatabaseService } from '../../../database/database.service';
import type {
  OrderContext,
  PaymentIntent,
  PaymentProvider,
  PaymentProviderName,
} from './payment.types';

/**
 * 个人收款码通道（无需商户资质，立即可用）。
 *
 * 微信/支付宝的个人收款码不提供「谁付了多少钱」的回调，这是平台的产品限制。
 * 因此到账确认只能由管理员在后台完成。为把人工成本压到最低，我们做了两件事：
 *   1) 应付金额带唯一分位尾数（OrdersService 负责分配），收款通知的金额可直接定位订单；
 *   2) 用户提交付款截图 + 备注，管理员在后台一屏内比对并一键确认。
 */
@Injectable()
export class ManualQrProvider implements PaymentProvider {
  readonly name: PaymentProviderName = 'manual_qr';
  readonly autoConfirm = false;

  constructor(private readonly db: DatabaseService) {}

  /** 取当前启用的收款码（sort_order 最小者优先）。 */
  async pickQrcode(): Promise<any | null> {
    const rows = await this.db.query<any[]>(
      'SELECT * FROM payment_qrcodes WHERE enabled = 1 ORDER BY sort_order, id LIMIT 1',
    );
    return rows[0] ?? null;
  }

  async createIntent(ctx: OrderContext): Promise<PaymentIntent> {
    const qr = await this.pickQrcode();
    if (!qr) {
      throw new BadRequestException(
        '收款方式尚未配置，请联系管理员在后台上传收款码后再试。',
      );
    }
    return {
      provider: this.name,
      requiresProof: true,
      qrcode: {
        id: qr.id,
        channel: qr.channel,
        label: qr.label || (qr.channel === 'alipay' ? '支付宝扫码' : '微信扫码'),
        accountNote: qr.account_note || '',
        imagePath: `/orders/qrcode/${qr.id}/image`,
      },
      hint: `请按订单金额 ¥${(ctx.payAmountCents / 100).toFixed(2)} 一分不差地付款，金额尾数是本单的识别码。`,
    };
  }
}
