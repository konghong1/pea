import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  ParseIntPipe,
  Post,
  Query,
  Res,
  UseGuards,
} from '@nestjs/common';
import { Response } from 'express';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { AdminGuard } from '../../common/guards/admin.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { OrdersService } from './orders.service';
import {
  CreateOrderDto,
  ReviewOrderDto,
  SubmitProofDto,
  UpsertQrcodeDto,
} from './orders.dto';

/**
 * 用户侧支付订单。
 *
 * 生命周期：POST /orders (下单) → 扫码付款 → POST /orders/:no/proof (提交凭证)
 *          → 轮询 GET /orders/:no 直到 status=paid
 */
@Controller('orders')
@UseGuards(JwtAuthGuard)
export class OrdersController {
  constructor(private readonly orders: OrdersService) {}

  /** 当前支付通道能力，前端据此决定是否展示"上传付款凭证"区块。 */
  @Get('payment-info')
  paymentInfo() {
    return this.orders.paymentInfo();
  }

  @Get()
  listMine(@CurrentUser() u: { sub: number }, @Query('limit') limit?: string) {
    return this.orders.listMyOrders(u.sub, limit ? parseInt(limit, 10) : 20);
  }

  @Post()
  create(@CurrentUser() u: { sub: number }, @Body() dto: CreateOrderDto) {
    return this.orders.createOrder(u.sub, dto.planId);
  }

  /** 收款码图片（登录可见，本就是给付款人扫的）。前端用 blob 方式拉取。 */
  @Get('qrcode/:id/image')
  async qrcodeImage(@Param('id', ParseIntPipe) id: number, @Res() res: Response) {
    const { stream, contentType } = await this.orders.qrcodeImage(id);
    res.setHeader('Content-Type', contentType);
    res.setHeader('Cache-Control', 'private, max-age=3600');
    stream.pipe(res);
  }

  @Get(':orderNo')
  getOne(@CurrentUser() u: { sub: number }, @Param('orderNo') orderNo: string) {
    return this.orders.getMyOrder(u.sub, orderNo);
  }

  @Post(':orderNo/proof')
  submitProof(
    @CurrentUser() u: { sub: number },
    @Param('orderNo') orderNo: string,
    @Body() dto: SubmitProofDto,
  ) {
    return this.orders.submitProof(u.sub, orderNo, dto.proofKey, dto.proofNote);
  }

  @Post(':orderNo/cancel')
  cancel(@CurrentUser() u: { sub: number }, @Param('orderNo') orderNo: string) {
    return this.orders.cancelOrder(u.sub, orderNo);
  }
}

/** 管理员：订单审核 + 收款码管理。 */
@Controller('admin/orders')
@UseGuards(JwtAuthGuard, AdminGuard)
export class AdminOrdersController {
  constructor(private readonly orders: OrdersService) {}

  @Get()
  list(@Query('status') status?: string, @Query('limit') limit?: string) {
    return this.orders.adminList(status, limit ? parseInt(limit, 10) : 50);
  }

  @Get('pending-count')
  pendingCount() {
    return this.orders.adminPendingCount();
  }

  /** 付款凭证截图（仅管理员，含用户个人支付信息）。 */
  @Get(':orderNo/proof')
  async proof(@Param('orderNo') orderNo: string, @Res() res: Response) {
    const { stream, contentType } = await this.orders.proofImage(orderNo);
    res.setHeader('Content-Type', contentType);
    res.setHeader('Cache-Control', 'private, max-age=600');
    stream.pipe(res);
  }

  /** 确认到账 → 立即发放权益（幂等，重复点击不会双发）。 */
  @Post(':orderNo/approve')
  approve(
    @CurrentUser() u: { sub: number },
    @Param('orderNo') orderNo: string,
    @Body() dto: ReviewOrderDto,
  ) {
    return this.orders.confirmPaid({
      orderNo,
      reviewerId: u.sub,
      reviewNote: dto.reviewNote,
      paidAmountCents: dto.paidAmountCents,
    });
  }

  @Post(':orderNo/reject')
  reject(
    @CurrentUser() u: { sub: number },
    @Param('orderNo') orderNo: string,
    @Body() dto: ReviewOrderDto,
  ) {
    return this.orders.rejectOrder(orderNo, u.sub, dto.reviewNote);
  }
}

@Controller('admin/payment-qrcodes')
@UseGuards(JwtAuthGuard, AdminGuard)
export class AdminQrcodesController {
  constructor(private readonly orders: OrdersService) {}

  @Get()
  list() {
    return this.orders.listQrcodes(true);
  }

  @Post()
  upsert(@Body() dto: UpsertQrcodeDto) {
    return this.orders.upsertQrcode(dto);
  }

  @Delete(':id')
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.orders.deleteQrcode(id);
  }
}

/**
 * 支付网关回调。
 *
 * ⚠️ 无 JwtAuthGuard —— 调用方是微信服务器，不可能带我们的 token。
 * 真实性由 APIv3 的 AES-256-GCM 解密保证：apiV3Key 仅商户与微信双方持有，
 * 解密成功（认证标签校验通过）即证明报文未被伪造或篡改。
 */
@Controller('pay/notify')
export class PayNotifyController {
  constructor(private readonly orders: OrdersService) {}

  @Post('wechat')
  async wechat(@Body() body: any, @Res() res: Response) {
    const result = await this.orders.handleWechatNotify(body);
    // 微信要求：非 SUCCESS 需返回非 2xx，才会触发重试
    res.status(result.code === 'SUCCESS' ? 200 : 500).json(result);
  }

  /**
   * 码支付/聚合支付回调。
   *
   * ⚠️ 同样无 JwtAuthGuard —— 调用方是码支付网关服务器。
   * 真实性由通信密钥签名验真保证（verifyNotify 验签通过即可信）。
   * 同时接收 @Body 与 @Query 并合并，兼容 POST(form/JSON) 与 GET(query) 两种回调形态。
   */
  @Post('codepay')
  async codepay(@Body() body: any, @Query() query: any, @Res() res: Response) {
    const payload = { ...(query || {}), ...(body || {}) };
    const result = await this.orders.handleCodepayNotify(payload);
    // 网关约定：非 SUCCESS 返回非 2xx 触发重试
    res.status(result.code === 'SUCCESS' ? 200 : 500).json(result);
  }
}
