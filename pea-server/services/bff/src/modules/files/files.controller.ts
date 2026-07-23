import {
  Body,
  Controller,
  Get,
  Post,
  Query,
  UseGuards,
  BadRequestException,
} from '@nestjs/common';
import { IsString, IsInt, IsOptional } from 'class-validator';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { FilesService } from './files.service';

class PresignDto {
  @IsString()
  key: string;

  @IsOptional()
  @IsInt()
  expiresSec?: number;
}

@Controller('files')
@UseGuards(JwtAuthGuard)
export class FilesController {
  constructor(private readonly files: FilesService) {}

  @Post('presign')
  async presign(@Body() dto: PresignDto, @CurrentUser() u: { sub: number }) {
    const url = await this.files.presignPut(dto.key, u.sub, dto.expiresSec ?? 600);
    return { key: dto.key, uploadUrl: url };
  }

  @Get('url')
  async url(@Query('key') key: string, @CurrentUser() u: { sub: number }) {
    if (!key) throw new BadRequestException('key required');
    return { key, downloadUrl: await this.files.presignGet(key, u.sub) };
  }
}
