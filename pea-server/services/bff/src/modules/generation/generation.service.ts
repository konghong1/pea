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

    // 1) 预扣 (强一致, 幂等)
    this.billing.preauthorize(userId, cost, `${idem}:preauth`);

    // 2) 受理 (交编排器落库+入队)
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
  }

  async getStatus(jobId: string) {
    return this.orch.getJob(jobId);
  }

  async listJobs(userId: number, limit = 20, cursor = 0) {
    if (limit > 100) throw new BadRequestException('limit too large');
    return this.orch.listJobs(userId, limit, cursor);
  }
}
