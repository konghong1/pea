import { Injectable, NestMiddleware, ForbiddenException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Request, Response, NextFunction } from 'express';

/**
 * 简单内存限流 (每 IP 每分钟 N 次). 生产环境替换为 Redis 令牌桶 (可水平扩展).
 * 配合架构风险 R1: 限流/断路器是成本失控头号风险的防线之一.
 */
@Injectable()
export class RateLimitMiddleware implements NestMiddleware {
  private hits = new Map<string, { count: number; resetAt: number }>();

  constructor(private readonly config: ConfigService) {}

  use(req: Request, res: Response, next: NextFunction) {
    const limit = this.config.get<number>('rateLimitPerMin') ?? 120;
    const ip = req.ip ?? 'unknown';
    const now = Date.now();
    const rec = this.hits.get(ip);
    if (!rec || rec.resetAt < now) {
      this.hits.set(ip, { count: 1, resetAt: now + 60_000 });
      return next();
    }
    rec.count += 1;
    if (rec.count > limit) {
      throw new ForbiddenException('rate limit exceeded');
    }
    next();
  }
}
