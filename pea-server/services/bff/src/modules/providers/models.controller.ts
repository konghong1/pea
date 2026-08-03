import {
  Body,
  Controller,
  Get,
  Post,
  Query,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { ModelsService } from './models.service';
import { EstimateDto } from './models.dto';

/** 用户侧: 可用模型列表 (标注是否解锁) + 价格预估。 */
@Controller('models')
@UseGuards(JwtAuthGuard)
export class ModelsController {
  constructor(private readonly models: ModelsService) {}

  @Get('available')
  available(
    @CurrentUser() u: { sub: number },
    @Query('type') type?: 'image' | 'video' | 'text' | 'audio' | '3d',
  ) {
    return this.models.listAvailable(u.sub, type);
  }

  @Post('estimate')
  estimate(@CurrentUser() u: { sub: number }, @Body() dto: EstimateDto) {
    return this.models.estimate(u.sub, dto.modelId, dto.params ?? {});
  }
}
