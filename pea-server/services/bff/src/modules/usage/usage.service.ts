import { Injectable } from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';

export interface RecordUsageInput {
  userId: number;
  nodeType: 'text' | 'image' | 'video';
  model?: string | null;
  provider?: string | null;
  platformConfigId?: string | null;
  jobId?: string | null;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}

/**
 * token 用量计量 (Phase3): 拥有 usage_records 表的写权限。
 * 文本聊天 (BFF SSE) 与图片/视频 (Orchestrator) 都向此表写审计记录。
 * 当前仅审计/统计, 不改计费公式 (决策 #3)。
 */
@Injectable()
export class UsageService {
  constructor(private readonly db: DatabaseService) {}

  async record(input: RecordUsageInput): Promise<void> {
    await this.db.query(
      `INSERT INTO usage_records
       (user_id, job_id, node_type, model, provider, platform_config_id, input_tokens, output_tokens, total_tokens)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        input.userId,
        input.jobId ?? null,
        input.nodeType,
        input.model ?? null,
        input.provider ?? null,
        input.platformConfigId ?? null,
        input.inputTokens | 0,
        input.outputTokens | 0,
        input.totalTokens | 0,
      ],
    );
  }

  /** 用户用量汇总 (前端展示/审计)。 */
  async summary(userId: number) {
    const rows = await this.db.query<any[]>(
      `SELECT node_type, COALESCE(SUM(input_tokens),0) AS input_tokens,
              COALESCE(SUM(output_tokens),0) AS output_tokens,
              COALESCE(SUM(total_tokens),0) AS total_tokens, COUNT(*) AS calls
       FROM usage_records WHERE user_id = ?
       GROUP BY node_type`,
      [userId],
    );
    return rows;
  }
}
