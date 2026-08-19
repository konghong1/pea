import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpException,
  HttpStatus,
} from '@nestjs/common';
import { Request, Response } from 'express';

/** 全局异常: 统一返回 { code, message }, 生产环境隐藏堆栈. */
@Catch()
export class HttpExceptionFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const res = ctx.getResponse<Response>();
    const req = ctx.getRequest<Request>();

    const status =
      exception instanceof HttpException
        ? exception.getStatus()
        : HttpStatus.INTERNAL_SERVER_ERROR;

    const message =
      exception instanceof HttpException
        ? exception.message
        : 'internal error';

    // 生产环境不返回请求路径，防止信息泄露
    const isProd = process.env.NODE_ENV === 'production';
    const response: Record<string, unknown> = {
      code: status,
      message,
      ts: new Date().toISOString(),
    };
    if (!isProd) {
      response['path'] = req.url;
    }
    res.status(status).json(response);
  }
}
