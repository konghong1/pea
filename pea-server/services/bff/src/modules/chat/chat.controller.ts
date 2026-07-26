import {
  Body,
  Controller,
  Post,
  Res,
  UseGuards,
} from '@nestjs/common';
import { Response } from 'express';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { ChatService } from './chat.service';
import { ChatStreamDto } from './chat.dto';

/**
 * 节点聊天 SSE 端点 (轻量, 与生成任务 WS 流分离)。
 * 前端用 fetch POST + ReadableStream 消费; 不使用 EventSource(GET) 以便携带 body。
 */
@Controller('chat')
@UseGuards(JwtAuthGuard)
export class ChatController {
  constructor(private readonly chat: ChatService) {}

  @Post('stream')
  async stream(
    @CurrentUser() u: { sub: number },
    @Body() dto: ChatStreamDto,
    @Res() res: Response,
  ) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    res.flushHeaders();

    const send = (event: string, data: any) => {
      res.write(`event: ${event}\n`);
      res.write(`data: ${JSON.stringify(data)}\n\n`);
    };

    try {
      await this.chat.streamChat(u.sub, dto, send);
    } catch (e: any) {
      send('error', { message: e?.message ?? 'stream failed', refunded: false });
    } finally {
      res.end();
    }
  }
}
