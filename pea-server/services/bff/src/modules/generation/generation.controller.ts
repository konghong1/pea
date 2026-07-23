import {
  Body,
  Controller,
  Get,
  Param,
  Post,
  Query,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { GenerationService } from './generation.service';
import { AcceptGenerationDto } from './generation.dto';

@Controller('generation')
@UseGuards(JwtAuthGuard)
export class GenerationController {
  constructor(private readonly gen: GenerationService) {}

  @Post('jobs')
  accept(@CurrentUser() u: { sub: number }, @Body() dto: AcceptGenerationDto) {
    return this.gen.accept(u.sub, dto);
  }

  @Get('jobs/:jobId')
  status(@Param('jobId') jobId: string) {
    return this.gen.getStatus(jobId);
  }

  @Get('jobs')
  list(
    @CurrentUser() u: { sub: number },
    @Query('limit') limit = 20,
    @Query('cursor') cursor = '0',
  ) {
    // cursor 为 ISO 时间戳字符串 (真实游标分页); '0'/空 表示从头. 不再强转 Number, 以免破坏时间戳游标.
    const c = cursor === '0' || cursor === '' ? 0 : cursor;
    return this.gen.listJobs(u.sub, Number(limit), c);
  }
}
