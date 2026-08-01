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
  private heartbeat?: ReturnType<typeof setInterval>;
  /** 心跳周期: 需小于 nginx proxy_read_timeout(默认 60s), 否则空闲连接会被网关静默切断。 */
  private static readonly HEARTBEAT_MS = 30_000;

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

    // 3) 心跳巡检: 清理死连接.
    //    无心跳时, 客户端异常掉线(休眠/断网/杀进程)的 socket 会长期滞留在 userSockets,
    //    dispatch 往死 socket 写数据被静默丢弃 —— 表现为前端「余额/任务状态偶发不更新」。
    this.heartbeat = setInterval(() => {
      for (const ws of this.wss.clients) {
        if (ws['isAlive'] === false) {
          this.detach(ws);
          ws.terminate();
          continue;
        }
        ws['isAlive'] = false;
        try {
          ws.ping();
        } catch {
          /* 发送失败下一轮会被 terminate */
        }
      }
    }, EventsGateway.HEARTBEAT_MS);
  }

  private onConnection(ws: WebSocket) {
    ws['isAlive'] = true;
    ws.on('pong', () => {
      ws['isAlive'] = true;
    });
    ws.on('message', (data) => {
      let msg: any;
      try {
        msg = JSON.parse(data.toString());
      } catch {
        return;
      }
      if (!msg) return;
      if (msg.type === 'auth') this.authenticate(ws, msg.token);
      // 应用层 ping: 部分代理会吞掉 WS 协议层 ping/pong, 客户端可用它保活
      else if (msg.type === 'ping') {
        ws['isAlive'] = true;
        if (ws.readyState === ws.OPEN) ws.send(JSON.stringify({ kind: 'pong' }));
      }
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
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.wss.close();
  }
}
