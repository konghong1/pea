import { Module } from '@nestjs/common';
import { OrdersService } from './orders.service';
import {
  OrdersController,
  AdminOrdersController,
  AdminQrcodesController,
  PayNotifyController,
} from './orders.controller';
import { ManualQrProvider } from './payment/manual-qr.provider';
import { WechatNativeProvider } from './payment/wechat-native.provider';
import { CodepayProvider } from './payment/codepay.provider';
import { AdminGuard } from '../../common/guards/admin.guard';
import { PlansModule } from '../plans/plans.module';
import { FilesModule } from '../files/files.module';

/**
 * 支付订单域：下单 → 付款 → 确认到账 → 发放权益。
 *
 * 依赖方向（ARCH §6）：orders → plans（发放）、orders → files（凭证/收款码对象读取）。
 * 两个支付通道 provider 都注册，运行时由 PEA_PAY_PROVIDER 选择，
 * 切换无需改动模块装配。
 */
@Module({
  imports: [PlansModule, FilesModule],
  controllers: [
    OrdersController,
    AdminOrdersController,
    AdminQrcodesController,
    PayNotifyController,
  ],
  providers: [OrdersService, ManualQrProvider, WechatNativeProvider, CodepayProvider, AdminGuard],
  exports: [OrdersService],
})
export class OrdersModule {}
