import {
  Body,
  Controller,
  Get,
  Post,
  Query,
  Res,
  UploadedFile,
  UseGuards,
  UseInterceptors,
  BadRequestException,
} from '@nestjs/common';
import { IsString, IsInt, IsOptional } from 'class-validator';
import { FileInterceptor } from '@nestjs/platform-express';
import { Response } from 'express';
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

  /** 前端经 BFF 代理上传（multipart），避免预签名 URL 的 host 绑定/跨域问题。 */
  @Post('upload')
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: 100 * 1024 * 1024 } }))
  async upload(
    @UploadedFile() file: any,
    @CurrentUser() u: { sub: number },
  ) {
    if (!file) throw new BadRequestException('file required');
    const key = `u:${u.sub}/uploads/${Date.now()}-${file.originalname}`;
    await this.files.putObject(key, file.buffer, file.mimetype);
    return { key };
  }

  /** 前端经 BFF 代理下载（同域流式返回），bucket 仍保持私有。 */
  @Get('download')
  async download(
    @Query('key') key: string,
    @Res() res: Response,
    @CurrentUser() u: { sub: number },
  ) {
    if (!key || !key.startsWith(`u:${u.sub}/`)) throw new BadRequestException('forbidden');
    try {
      const stat = await this.files.statObject(key);
      const stream = await this.files.getObjectStream(key);
      const ct = stat.metaData?.['content-type'] || stat.metaData?.['Content-Type'] || 'application/octet-stream';
      res.setHeader('Content-Type', ct);
      res.setHeader('Cache-Control', 'private, max-age=31536000');
      stream.pipe(res);
    } catch {
      throw new BadRequestException('not found');
    }
  }
}
