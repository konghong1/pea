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
    resultUrls?: string[];
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
export declare const EVENTS_CHANNEL = "pea:events";
export declare const GEN_QUEUE = "pea:gen:queue";
