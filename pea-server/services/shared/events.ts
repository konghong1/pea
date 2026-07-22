/**
 * pea Creative OS — 跨服务事件契约 (TypeScript 镜像)
 *
 * 这些事件在 Redis 频道 `pea:events` 上发布，由 BFF 订阅并转发给前端 WebSocket。
 * Python 侧有完全一致的镜像: services/shared/events.py —— 修改任一侧必须同步另一侧。
 *
 * 事件流向:
 *   Generation Orchestrator --publish--> Redis(pea:events) --subscribe--> BFF --WS--> Web
 */

export type JobType = 'image' | 'video' | 'text';
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'refunded';

/** 生成任务状态变更事件 (orchestrator -> bff) */
export interface JobUpdatedEvent {
  kind: 'job.updated';
  jobId: string;
  userId: number;
  type: JobType;
  status: JobStatus;
  /** 0~1 进度, running 阶段有效 */
  progress?: number;
  /** 完成后媒体 URL */
  resultUrl?: string | null;
  /** 失败原因 */
  error?: string | null;
  /** 本次消耗 Tapies (done 时回填) */
  cost?: number;
  ts: number;
}

/** 余额变更事件 (bff billing -> bff ws, 或 orchestrator 退款后 bff 发出) */
export interface BalanceChangedEvent {
  kind: 'balance.changed';
  userId: number;
  balance: number;
  delta: number;
  reason: 'preauth' | 'confirm' | 'refund';
  ts: number;
}

/** 通用通知事件 (bff -> web) */
export interface NotificationEvent {
  kind: 'notification';
  userId: number;
  title: string;
  body: string;
  level: 'info' | 'success' | 'warning' | 'error';
  ts: number;
}

export type PeaEvent = JobUpdatedEvent | BalanceChangedEvent | NotificationEvent;

/** Redis 频道名 */
export const EVENTS_CHANNEL = 'pea:events';
/** 生成任务队列 (Redis Streams) */
export const GEN_QUEUE = 'pea:gen:queue';
