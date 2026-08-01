import {
  Injectable,
  NotFoundException,
  BadRequestException,
  ForbiddenException,
  Logger,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { DatabaseService } from '../../database/database.service';
import { FilesService } from '../files/files.service';
import { PlansService } from '../plans/plans.service';
import { ManualQrProvider } from './payment/manual-qr.provider';
import { WechatNativeProvider } from './payment/wechat-native.provider';
import { CodepayProvider } from './payment/codepay.provider';
import type { PaymentIntent, PaymentProvider } from './payment/payment.types';

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
  amountCents: number;
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
  /** 管理员视图附带 */
  userId?: number;
  userEmail?: string;
  userName?: string;
}

const STATUS_TEXT: Record<OrderStatus, string> = {
  pending: '待付款',
  submitted: '待确认到账',
  paid: '已开通',
  rejected: '已驳回',
  cancelled: '已取消',
  expired: '已超时',
};

/** 可被审核推进的状态（paid 也允许，用于发放失败后的补发重试）。 */
const REVIEWABLE: OrderStatus[] = ['pending', 'submitted', 'paid'];

/**
 * 支付订单域。
 *
 * 核心不变式：**权益只能由订单驱动发放**。
 *   - 用户自助 purchase() 已默认关闭（PEA_ALLOW_SELF_PURCHASE=0）
 *   - 唯一发放入口是 confirmPaid()，它要求订单已确认到账
 *   - 发放幂等键固定为 `order:{orderNo}`，一单只可能到账一次，
 *     人工确认与支付回调重复触发都不会双发
 *
 * 人工确认路径的对账设计：
 *   个人收款码没有回调，无法自动知道「谁付了多少」。为把人工比对成本降到最低，
 *   下单时给应付金额分配一个 0~99 分的随机尾数，并保证「同一时刻所有未结束订单的
 *   应付金额互不相同」。管理员看到收款通知里的 ¥19.87 就能唯一定位到订单。
 */
@Injectable()
export class OrdersService {
  private readonly logger = new Logger(OrdersService.name);

  constructor(
    private readonly db: DatabaseService,
    private readonly config: ConfigService,
    private readonly files: FilesService,
    private readonly plans: PlansService,
    private readonly manualQr: ManualQrProvider,
    private readonly wechat: WechatNativeProvider,
    private readonly codepay: CodepayProvider,
  ) {}

  private payCfg() {
    return this.config.get('payment') as {
      provider: 'manual_qr' | 'wechat_native' | 'codepay';
      orderTtlMinutes: number;
      amountFingerprint: boolean;
    };
  }

  private provider(): PaymentProvider {
    const p = this.payCfg().provider;
    if (p === 'wechat_native') return this.wechat;
    if (p === 'codepay') return this.codepay;
    return this.manualQr;
  }

  /** 当前支付通道能力，供前端决定是否展示"上传付款凭证"。 */
  paymentInfo() {
    const p = this.provider();
    return {
      provider: p.name,
      autoConfirm: p.autoConfirm,
      requiresProof: !p.autoConfirm,
    };
  }

  // ── 下单 ──────────────────────────────────────────────────────

  /**
   * 创建订单。同一用户对同一套餐若已有未结束订单，直接复用（避免重复下单刷金额尾数）。
   */
  async createOrder(userId: number, planId: string): Promise<{ order: OrderView; intent: PaymentIntent }> {
    await this.expireStale();

    const planRows = await this.db.query<any[]>(
      'SELECT * FROM billing_plans WHERE id = ? AND enabled = 1',
      [planId],
    );
    const plan = planRows[0];
    if (!plan) throw new NotFoundException('套餐不存在或已下架');
    if (plan.price_cents <= 0) {
      throw new BadRequestException('免费套餐无需购买，注册时已发放权益');
    }

    // 复用未结束的同套餐订单：金额尾数保持不变，用户重开弹窗仍是同一张单
    const existing = await this.db.query<any[]>(
      `SELECT * FROM payment_orders
       WHERE user_id = ? AND plan_id = ? AND status IN ('pending','submitted') AND expires_at > NOW(3)
       ORDER BY id DESC LIMIT 1`,
      [userId, planId],
    );
    if (existing.length) {
      const row = existing[0];
      return { order: toView(row), intent: await this.buildIntent(row) };
    }

    const ttlMin = Math.max(5, this.payCfg().orderTtlMinutes);
    const expiresAt = new Date(Date.now() + ttlMin * 60000);
    const payAmount = await this.allocatePayAmount(plan.price_cents);
    const orderNo = genOrderNo();

    await this.db.query(
      `INSERT INTO payment_orders
        (order_no, user_id, plan_id, plan_name, plan_level, tapies, duration_days,
         amount_cents, pay_amount_cents, provider, status, expires_at)
       VALUES (?,?,?,?,?,?,?,?,?,?, 'pending', ?)`,
      [
        orderNo, userId, planId, plan.name, plan.plan_level, plan.tapies,
        plan.duration_days, plan.price_cents, payAmount, this.provider().name, expiresAt,
      ],
    );

    const rows = await this.db.query<any[]>(
      'SELECT * FROM payment_orders WHERE order_no = ?',
      [orderNo],
    );
    const row = rows[0];
    const intent = await this.buildIntent(row);
    // 记录本单最终使用的收款码，便于事后对账
    if (intent.qrcode?.id) {
      await this.db.query('UPDATE payment_orders SET qrcode_id = ? WHERE order_no = ?', [
        intent.qrcode.id, orderNo,
      ]);
    }
    return { order: toView(row), intent };
  }

  private async buildIntent(row: any): Promise<PaymentIntent> {
    return this.provider().createIntent({
      orderNo: row.order_no,
      userId: row.user_id,
      planId: row.plan_id,
      planName: row.plan_name,
      payAmountCents: row.pay_amount_cents,
      expiresAt: new Date(row.expires_at),
    });
  }

  /**
   * 分配带唯一尾数的应付金额。
   * 在 [base, base+99] 中挑一个当前未被任何未结束订单占用的值；
   * 极端情况（100 个同价订单同时在途）退化为基准价，人工靠截图比对。
   */
  private async allocatePayAmount(baseCents: number): Promise<number> {
    if (!this.payCfg().amountFingerprint) return baseCents;
    const taken = await this.db.query<any[]>(
      `SELECT pay_amount_cents FROM payment_orders
       WHERE status IN ('pending','submitted') AND expires_at > NOW(3)
         AND pay_amount_cents BETWEEN ? AND ?`,
      [baseCents, baseCents + 99],
    );
    const used = new Set(taken.map((r) => r.pay_amount_cents));
    // 从随机偏移开始探测，避免所有订单都集中在低位尾数
    const start = Math.floor(Math.random() * 100);
    for (let i = 0; i < 100; i++) {
      const candidate = baseCents + ((start + i) % 100);
      if (!used.has(candidate)) return candidate;
    }
    return baseCents;
  }

  // ── 用户侧 ────────────────────────────────────────────────────

  async getMyOrder(userId: number, orderNo: string): Promise<{ order: OrderView; intent?: PaymentIntent }> {
    await this.expireStale();
    const row = await this.mustOwn(userId, orderNo);
    const order = toView(row);
    // 仍可支付的订单附带支付信息，供前端刷新弹窗
    if (row.status === 'pending' || row.status === 'submitted') {
      try {
        return { order, intent: await this.buildIntent(row) };
      } catch {
        return { order };
      }
    }
    return { order };
  }

  async listMyOrders(userId: number, limit = 20): Promise<OrderView[]> {
    await this.expireStale();
    const rows = await this.db.query<any[]>(
      'SELECT * FROM payment_orders WHERE user_id = ? ORDER BY id DESC LIMIT ?',
      [userId, Math.min(100, Math.max(1, limit))],
    );
    return rows.map(toView);
  }

  /** 用户提交付款凭证（截图 key + 备注），订单进入待确认队列。 */
  async submitProof(
    userId: number,
    orderNo: string,
    proofKey?: string,
    proofNote?: string,
  ): Promise<OrderView> {
    await this.expireStale();
    const row = await this.mustOwn(userId, orderNo);
    if (row.status === 'paid') throw new BadRequestException('该订单已开通，无需重复提交');
    if (row.status !== 'pending' && row.status !== 'submitted') {
      throw new BadRequestException(`订单当前状态为「${STATUS_TEXT[row.status as OrderStatus]}」，无法提交凭证`);
    }
    // 凭证必须位于提交者自己的对象命名空间下，防越权引用他人文件
    if (proofKey && !proofKey.startsWith(`u:${userId}/`)) {
      throw new ForbiddenException('非法的凭证文件');
    }
    await this.db.query(
      `UPDATE payment_orders
         SET status = 'submitted', proof_key = COALESCE(?, proof_key), proof_note = COALESCE(?, proof_note)
       WHERE order_no = ?`,
      [proofKey ?? null, proofNote ?? null, orderNo],
    );
    return toView(await this.mustOwn(userId, orderNo));
  }

  async cancelOrder(userId: number, orderNo: string): Promise<OrderView> {
    const row = await this.mustOwn(userId, orderNo);
    if (row.status !== 'pending' && row.status !== 'submitted') {
      throw new BadRequestException('该订单已结束，无法取消');
    }
    await this.db.query(
      "UPDATE payment_orders SET status = 'cancelled' WHERE order_no = ?",
      [orderNo],
    );
    return toView(await this.mustOwn(userId, orderNo));
  }

  private async mustOwn(userId: number, orderNo: string): Promise<any> {
    const rows = await this.db.query<any[]>(
      'SELECT * FROM payment_orders WHERE order_no = ?',
      [orderNo],
    );
    const row = rows[0];
    if (!row) throw new NotFoundException('订单不存在');
    if (row.user_id !== userId) throw new ForbiddenException('无权访问该订单');
    return row;
  }

  // ── 管理员侧 ──────────────────────────────────────────────────

  async adminList(status?: string, limit = 50): Promise<OrderView[]> {
    await this.expireStale();
    const where: string[] = [];
    const params: any[] = [];
    if (status && status !== 'all') {
      where.push('o.status = ?');
      params.push(status);
    }
    params.push(Math.min(200, Math.max(1, limit)));
    const rows = await this.db.query<any[]>(
      `SELECT o.*, u.email AS user_email, u.display_name AS user_name
       FROM payment_orders o JOIN users u ON u.id = o.user_id
       ${where.length ? 'WHERE ' + where.join(' AND ') : ''}
       ORDER BY
         CASE o.status WHEN 'submitted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
         o.id DESC
       LIMIT ?`,
      params,
    );
    return rows.map((r) => ({
      ...toView(r),
      userId: r.user_id,
      userEmail: r.user_email,
      userName: r.user_name,
    }));
  }

  /** 待办计数，用于后台角标。 */
  async adminPendingCount(): Promise<{ submitted: number; pending: number }> {
    const rows = await this.db.query<any[]>(
      `SELECT status, COUNT(*) AS n FROM payment_orders
       WHERE status IN ('submitted','pending') GROUP BY status`,
    );
    const m = Object.fromEntries(rows.map((r) => [r.status, Number(r.n)]));
    return { submitted: m.submitted ?? 0, pending: m.pending ?? 0 };
  }

  /**
   * 确认到账并发放权益。人工审核与支付回调共用此入口。
   *
   * 两阶段设计（关键）：
   *   ① 事务内把订单置为 paid 并写审核轨迹 —— 保证"确认到账"这个事实先落库；
   *   ② 事务外调 grantEntitlement（自身也是事务 + 幂等）—— 发放。
   * 若 ② 失败，订单停在 paid/granted=0，管理员可再点一次「确认到账」触发补发，
   * 幂等键相同因此绝不会双发。这比"发放和订单同事务"更耐操：
   * 发放涉及账户行锁，与订单表混在一个长事务里会放大锁竞争。
   */
  async confirmPaid(opts: {
    orderNo: string;
    reviewerId?: number;
    reviewNote?: string;
    paidAmountCents?: number;
    externalTxnId?: string;
  }): Promise<OrderView> {
    const { orderNo } = opts;

    const row = await this.db.transaction(async (conn) => {
      const [rows] = await conn.query(
        'SELECT * FROM payment_orders WHERE order_no = ? FOR UPDATE',
        [orderNo],
      );
      const o = (rows as any[])[0];
      if (!o) throw new NotFoundException('订单不存在');
      if (!REVIEWABLE.includes(o.status)) {
        throw new BadRequestException(
          `订单当前状态为「${STATUS_TEXT[o.status as OrderStatus]}」，无法确认到账`,
        );
      }
      if (o.status === 'paid' && o.granted) {
        // 已完成，直接幂等返回
        return o;
      }
      await conn.query(
        `UPDATE payment_orders
            SET status = 'paid', reviewer_id = ?, reviewed_at = NOW(3),
                review_note = COALESCE(?, review_note),
                paid_amount_cents = COALESCE(?, paid_amount_cents, pay_amount_cents),
                external_txn_id = COALESCE(?, external_txn_id)
          WHERE order_no = ?`,
        [
          opts.reviewerId ?? null,
          opts.reviewNote ?? null,
          opts.paidAmountCents ?? null,
          opts.externalTxnId ?? null,
          orderNo,
        ],
      );
      const [after] = await conn.query('SELECT * FROM payment_orders WHERE order_no = ?', [orderNo]);
      return (after as any[])[0];
    });

    if (row.granted) return toView(row);

    // 幂等键锁定到订单号：人工重复点击、回调重发、补发重试，都只发放一次
    await this.plans.grantEntitlement(
      row.user_id,
      {
        planId: row.plan_id,
        planLevel: row.plan_level,
        tapies: row.tapies,
        durationDays: row.duration_days,
        priceCents: row.amount_cents,
      },
      `order:${orderNo}`,
    );
    await this.db.query('UPDATE payment_orders SET granted = 1 WHERE order_no = ?', [orderNo]);
    this.logger.log(`order ${orderNo} granted: user=${row.user_id} plan=${row.plan_id}`);

    const finalRows = await this.db.query<any[]>(
      'SELECT * FROM payment_orders WHERE order_no = ?',
      [orderNo],
    );
    return toView(finalRows[0]);
  }

  async rejectOrder(orderNo: string, reviewerId: number, reviewNote?: string): Promise<OrderView> {
    const rows = await this.db.query<any[]>(
      'SELECT * FROM payment_orders WHERE order_no = ?',
      [orderNo],
    );
    const o = rows[0];
    if (!o) throw new NotFoundException('订单不存在');
    if (o.status === 'paid') throw new BadRequestException('该订单已开通权益，不能驳回');
    await this.db.query(
      `UPDATE payment_orders
          SET status = 'rejected', reviewer_id = ?, reviewed_at = NOW(3), review_note = ?
        WHERE order_no = ?`,
      [reviewerId, reviewNote ?? null, orderNo],
    );
    const after = await this.db.query<any[]>(
      'SELECT * FROM payment_orders WHERE order_no = ?',
      [orderNo],
    );
    return toView(after[0]);
  }

  /** 超时未支付的订单置 expired，同时释放其占用的金额尾数。懒执行，无需定时任务。 */
  private async expireStale(): Promise<void> {
    await this.db.query(
      "UPDATE payment_orders SET status = 'expired' WHERE status = 'pending' AND expires_at < NOW(3)",
    );
  }

  // ── 凭证 / 收款码图片读取 ─────────────────────────────────────

  /** 收款码图片：所有登录用户可读（本来就要展示给付款人）。 */
  async qrcodeImage(qrcodeId: number) {
    const rows = await this.db.query<any[]>(
      'SELECT * FROM payment_qrcodes WHERE id = ?',
      [qrcodeId],
    );
    const qr = rows[0];
    if (!qr) throw new NotFoundException('收款码不存在');
    return this.readObject(qr.image_key);
  }

  /** 付款凭证：仅管理员可读（含用户个人支付信息）。 */
  async proofImage(orderNo: string) {
    const rows = await this.db.query<any[]>(
      'SELECT proof_key FROM payment_orders WHERE order_no = ?',
      [orderNo],
    );
    if (!rows.length || !rows[0].proof_key) throw new NotFoundException('该订单无付款凭证');
    return this.readObject(rows[0].proof_key);
  }

  private async readObject(key: string) {
    try {
      const stat = await this.files.statObject(key);
      const stream = await this.files.getObjectStream(key);
      const ct =
        stat.metaData?.['content-type'] ||
        stat.metaData?.['Content-Type'] ||
        'application/octet-stream';
      return { stream, contentType: ct as string };
    } catch {
      throw new NotFoundException('文件不存在');
    }
  }

  // ── 收款码 CRUD (管理员) ──────────────────────────────────────

  async listQrcodes(includeDisabled = true) {
    const rows = await this.db.query<any[]>(
      includeDisabled
        ? 'SELECT * FROM payment_qrcodes ORDER BY sort_order, id'
        : 'SELECT * FROM payment_qrcodes WHERE enabled = 1 ORDER BY sort_order, id',
    );
    return rows.map((r) => ({
      id: r.id,
      channel: r.channel,
      label: r.label,
      accountNote: r.account_note,
      imageKey: r.image_key,
      imagePath: `/orders/qrcode/${r.id}/image`,
      enabled: !!r.enabled,
      sortOrder: r.sort_order,
    }));
  }

  async upsertQrcode(input: {
    id?: number;
    channel?: string;
    label?: string;
    accountNote?: string;
    imageKey?: string;
    enabled?: boolean;
    sortOrder?: number;
  }) {
    if (input.id) {
      await this.db.query(
        `UPDATE payment_qrcodes
            SET channel = COALESCE(?, channel), label = COALESCE(?, label),
                account_note = COALESCE(?, account_note), image_key = COALESCE(?, image_key),
                enabled = COALESCE(?, enabled), sort_order = COALESCE(?, sort_order)
          WHERE id = ?`,
        [
          input.channel ?? null, input.label ?? null, input.accountNote ?? null,
          input.imageKey ?? null,
          input.enabled === undefined ? null : input.enabled ? 1 : 0,
          input.sortOrder ?? null, input.id,
        ],
      );
      return (await this.listQrcodes()).find((q) => q.id === input.id);
    }
    if (!input.imageKey) throw new BadRequestException('请先上传收款码图片');
    const res: any = await this.db.query(
      `INSERT INTO payment_qrcodes (channel, label, image_key, account_note, enabled, sort_order)
       VALUES (?,?,?,?,?,?)`,
      [
        input.channel ?? 'wechat', input.label ?? '', input.imageKey,
        input.accountNote ?? '', input.enabled === false ? 0 : 1, input.sortOrder ?? 0,
      ],
    );
    return (await this.listQrcodes()).find((q) => q.id === res.insertId);
  }

  async deleteQrcode(id: number) {
    const res: any = await this.db.query('DELETE FROM payment_qrcodes WHERE id = ?', [id]);
    if (res.affectedRows === 0) throw new NotFoundException('收款码不存在');
    return { ok: true as const };
  }

  // ── 支付网关回调 ──────────────────────────────────────────────

  /**
   * 微信支付回调。与人工确认走同一个 confirmPaid()，因此：
   *   - 回调重发不会重复发放（幂等键 order:{orderNo}）
   *   - 人工已确认过的订单再收到回调也安全
   */
  async handleWechatNotify(body: any): Promise<{ code: string; message: string }> {
    const resource = body?.resource;
    if (!resource?.ciphertext) {
      return { code: 'FAIL', message: '缺少 resource' };
    }
    let payload;
    try {
      payload = this.wechat.decryptNotify(resource);
    } catch (e) {
      this.logger.warn(`wxpay notify decrypt failed: ${(e as Error).message}`);
      return { code: 'FAIL', message: '解密失败' };
    }
    if (payload.trade_state !== 'SUCCESS') {
      return { code: 'SUCCESS', message: 'ignored' };
    }
    try {
      await this.confirmPaid({
        orderNo: payload.out_trade_no,
        reviewNote: '微信支付自动确认',
        paidAmountCents: payload.amount?.payer_total ?? payload.amount?.total,
        externalTxnId: payload.transaction_id,
      });
    } catch (e) {
      this.logger.error(`wxpay notify grant failed ${payload.out_trade_no}: ${(e as Error).message}`);
      // 返回非 SUCCESS 让微信按策略重试
      return { code: 'FAIL', message: '处理失败' };
    }
    return { code: 'SUCCESS', message: 'OK' };
  }

  /**
   * 码支付/聚合支付回调。与人工确认、微信回调共用同一个 confirmPaid()，
   * 因此同样幂等、重发安全。
   *
   * 真实性由网关签名的验真保证：通信密钥仅商户与网关双方持有，验签通过即证明报文未被伪造。
   */
  async handleCodepayNotify(body: any): Promise<{ code: string; message: string }> {
    if (!this.codepay.isConfigured()) {
      this.logger.warn('codepay notify received but provider not configured');
      return { code: 'FAIL', message: '未配置' };
    }
    const parsed = this.codepay.verifyNotify(body || {});
    if (!parsed) {
      return { code: 'FAIL', message: '签名校验失败' };
    }
    try {
      await this.confirmPaid({
        orderNo: parsed.orderNo,
        reviewNote: '码支付自动确认',
        paidAmountCents: parsed.paidAmountCents,
        externalTxnId: parsed.tradeNo || undefined,
      });
    } catch (e) {
      this.logger.error(`codepay notify grant failed ${parsed.orderNo}: ${(e as Error).message}`);
      // 返回非 SUCCESS 让网关按策略重试
      return { code: 'FAIL', message: '处理失败' };
    }
    return { code: 'SUCCESS', message: 'OK' };
  }
}

function genOrderNo(): string {
  const d = new Date();
  const p = (n: number, w = 2) => String(n).padStart(w, '0');
  const ts =
    `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
    `${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  const rand = Math.random().toString(36).slice(2, 8).toUpperCase();
  return `PEA${ts}${rand}`;
}

function toView(r: any): OrderView {
  const status = r.status as OrderStatus;
  return {
    orderNo: r.order_no,
    planId: r.plan_id,
    planName: r.plan_name,
    planLevel: r.plan_level,
    tapies: r.tapies,
    durationDays: r.duration_days,
    amountCents: r.amount_cents,
    payAmountCents: r.pay_amount_cents,
    provider: r.provider,
    status,
    statusText: STATUS_TEXT[status] ?? status,
    proofKey: r.proof_key ?? null,
    proofNote: r.proof_note ?? null,
    reviewNote: r.review_note ?? null,
    granted: !!r.granted,
    expiresAt: toIso(r.expires_at),
    createdAt: toIso(r.created_at),
    reviewedAt: r.reviewed_at ? toIso(r.reviewed_at) : null,
  };
}

function toIso(v: any): string {
  if (!v) return '';
  return v instanceof Date ? v.toISOString() : new Date(v).toISOString();
}
