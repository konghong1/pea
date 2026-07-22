import { Injectable, OnModuleInit, OnApplicationShutdown } from '@nestjs/common';
import { HttpAdapterHost } from '@nestjs/core';
import type { Server as HttpServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import { RedisPubSubService } from '../../infra/redis-pubsub.service';

/**
 * 实时推送网关 (ADR-007 WS).
 * 直接用原生 ws 库挂载到 Nest HTTP 服务器的 upgrade 事件, 不依赖 @nestjs/platform-* (避免驱动缺失).
 * 前端连接后发 { type:'auth', token } 完成鉴权; 之后按 userId 接收:
 *   job.updated / balance.changed / notification 三类事件.
 */
@Injectable()
export class EventsGateway implements OnModuleInit, OnApplicationShutdown {
  private wss = new WebSocketServer({ noServer: true });
  private userSockets = new Map<number, Set<WebSocket>>();

  constructor(
    private readonly redis: RedisPubSubService,
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
    private readonly adapterHost: HttpAdapterHost,
  ) {}

  onModuleInit() {
    // 1) Redis 事件订阅 -> 按 userId 推送给前端
    //    订阅动作由 RedisPubSubService 在连接 'ready' 后再执行, 避免 subscriber 模式冲突.
    this.redis.onMessage((_ch: string, payload: string) => {
      try {
        this.dispatch(JSON.parse(payload));
      } catch {
        /* ignore malformed */
      }
    });

    // 2) 挂到 Nest HTTP 服务器的 upgrade 事件, 处理 /ws 路径
    const httpServer = this.adapterHost.httpAdapter.getHttpServer() as HttpServer;
    httpServer.on('upgrade', (req, socket, head) => {
      if (req.url !== '/ws') {
        socket.destroy();
        return;
      }
      this.wss.handleUpgrade(req, socket, head, (ws) => this.onConnection(ws));
    });
  }

  private onConnection(ws: WebSocket) {
    ws.on('message', (data) => {
      let msg: any;
      try {
        msg = JSON.parse(data.toString());
      } catch {
        return;
      }
      if (msg && msg.type === 'auth') this.authenticate(ws, msg.token);
    });
    ws.on('close', () => this.detach(ws));
    ws.on('error', () => this.detach(ws));
  }

  private authenticate(ws: WebSocket, token?: string) {
    try {
      const decoded = this.jwt.verify(token ?? '', {
        secret: this.config.get('jwt.secret'),
      });
      const userId = decoded.sub;
      ws['userId'] = userId;
      if (!this.userSockets.has(userId)) this.userSockets.set(userId, new Set());
      this.userSockets.get(userId)!.add(ws);
      ws.send(JSON.stringify({ kind: 'auth.ok', userId }));
    } catch {
      ws.send(JSON.stringify({ kind: 'auth.error' }));
    }
  }

  private detach(ws: WebSocket) {
    const userId = ws['userId'];
    if (userId != null) this.userSockets.get(userId)?.delete(ws);
  }

  private dispatch(event: { userId?: number }) {
    if (!event.userId) return;
    const sockets = this.userSockets.get(event.userId);
    if (!sockets) return;
    for (const ws of sockets) {
      if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(event));
    }
  }

  onApplicationShutdown() {
    this.wss.close();
  }
}
