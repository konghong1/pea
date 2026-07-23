import { Injectable, BadRequestException } from '@nestjs/common';
import { BillingService } from '../billing/billing.service';
import { OrchestratorHttpClient } from '../orchestrator-client/orchestrator-http.service';
import { AcceptGenerationDto } from './generation.dto';

const DEFAULT_COST = 10;

/**
 * 生成受理 (T-GEN-02): 校验 -> 预扣积分 -> 写 job(交编排器) -> 返 jobId (p95<2s).
 * 关键点: 预扣失败直接返回明确错误; 预扣成功但下游失败时, 由 orchestrator 补偿退款.
 */
@Injectable()
export class GenerationService {
  constructor(
    private readonly billing: BillingService,
    private readonly orch: OrchestratorHttpClient,
  ) {}

  async accept(userId: number, dto: AcceptGenerationDto) {
    const cost = dto.costTapies ?? DEFAULT_COST;
    const idem = dto.idempotencyKey ?? `${userId}:${Date.now()}:${Math.random().toString(36).slice(2)}`;

    // 1) 预扣 (强一致, 幂等). 必须 await: 原实现未 await, 下游失败时积分已扣却无退款 -> 白送.
    await this.billing.preauthorize(userId, cost, `${idem}:preauth`);

    // 2) 受理 (交编排器落库+入队). 若受理失败, 立即本地退款, 避免积分悬空 (资深开发复核 T-GEN-02).
    //    说明: 仅当 job 未成功创建时才本地退; job 创建成功后由 orchestrator 失败补偿负责退款,
    //    二者 txn_id 不同键 (预扣=${idem}:preauth, 退款=${job_id}:refund) 互不冲突, 不会双退。
    try {
      const job = await this.orch.acceptJob({
        user_id: userId,
        type: dto.type,
        prompt: dto.prompt,
        model: dto.model,
        priority: dto.priority ?? 'normal',
        idempotency_key: idem,
        cost_tapies: cost,
      });

      return { jobId: job.jobId, status: job.status, costTapies: job.cost_tapies };
    } catch (err) {
      await this.billing.refund(userId, cost, `${idem}:refund`);
      throw err;
    }
  }

  async getStatus(jobId: string) {
    return this.orch.getJob(jobId);
  }

  async listJobs(userId: number, limit = 20, cursor: string | number = 0) {
    if (limit > 100) throw new BadRequestException('limit too large');
    return this.orch.listJobs(userId, limit, cursor);
  }
}
