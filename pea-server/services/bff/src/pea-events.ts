/**
 * 跨服务事件契约 (BFF 侧本地定义, single import 点).
 *
 * 与 services/shared/events.ts (TS 镜像) 及 services/shared/events.py (Python 镜像)
 * 保持完全一致 —— 修改任一侧必须同步另一侧。
 *
 * 事件流向:
 *   Generation Orchestrator --publish--> Redis(pea:events) --subscribe--> BFF --WS--> Web
 */

export type JobType = 'image' | 'video' | 'text';
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'refunded';

export interface JobUpdatedEvent {
  kind: 'job.updated';
  jobId: string;
  userId: number;
  type: JobType;
  status: JobStatus;
  progress?: number;
  resultUrl?: string | null;
  error?: string | null;
  cost?: number;
  ts: number;
}

export interface BalanceChangedEvent {
  kind: 'balance.changed';
  userId: number;
  balance: number;
  delta: number;
  reason: 'preauth' | 'confirm' | 'refund';
  ts: number;
}

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
