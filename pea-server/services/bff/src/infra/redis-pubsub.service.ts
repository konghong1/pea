import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Redis } from 'ioredis';
import { EVENTS_CHANNEL } from '../pea-events';

/**
 * 单例 Redis: 既用于发布跨服务事件 (BFF -> 前端), 也用于 gateway 订阅.
 * 事件契约见 services/shared/events.ts (Python 镜像 events.py).
 */
@Injectable()
export class RedisPubSubService implements OnModuleInit, OnModuleDestroy {
  private publisher: Redis;
  private subscriber: Redis;
  private messageHandlers: Array<(channel: string, payload: string) => void> = [];

  constructor(private readonly config: ConfigService) {}

  onModuleInit() {
    const url = this.config.get<string>('redis.url') ?? 'redis://localhost:6379/0';
    this.publisher = new Redis(url);
    this.subscriber = new Redis(url);
    // ioredis 连接就绪后会发 INFO 做 ready 检查. 若在连接就绪前调用 subscribe(),
    // 连接会提前进入 subscriber 模式, 导致 INFO 被拒("only subscriber commands may be used"),
    // 进而 'ready' 事件永不触发、SUBSCRIBE 永不发出 -> 无人订阅事件通道 -> WS 推送失效.
    // 因此必须在 'ready' 之后再订阅.
    this.subscriber.on('error', () => {
      /* ioredis 会自动重连, 此处吞掉避免未处理错误导致进程退出 */
    });
    this.subscriber.on('ready', () => {
      this.subscriber.subscribe(EVENTS_CHANNEL).catch(() => {
        /* 订阅失败时下次 ready 会重试; 忽略单次失败 */
      });
    });
    this.subscriber.on('message', (channel: string, payload: string) => {
      for (const h of this.messageHandlers) h(channel, payload);
    });
  }

  /** 注册跨服务事件消息处理器 (gateway 用于转发到 WebSocket). */
  onMessage(handler: (channel: string, payload: string) => void): void {
    this.messageHandlers.push(handler);
  }

  async publish(channel: string, event: Record<string, any>): Promise<void> {
    await this.publisher.publish(channel, JSON.stringify(event));
  }

  getSubscriber(): Redis {
    return this.subscriber;
  }

  onModuleDestroy() {
    this.publisher?.disconnect();
    this.subscriber?.disconnect();
  }
}
