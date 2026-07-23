import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import axios, { AxiosInstance } from 'axios';

/**
 * BFF -> Generation Orchestrator 的 HTTP 客户端.
 * 模块边界: BFF 不直连 generation_jobs 表, 只通过本客户端调用编排器 API (ARCH §6).
 */
@Injectable()
export class OrchestratorHttpClient {
  private http: AxiosInstance;

  constructor(config: ConfigService) {
    this.http = axios.create({
      baseURL: config.get<string>('orchestratorUrl'),
      timeout: 5000,
    });
  }

  async acceptJob(payload: Record<string, any>) {
    const { data } = await this.http.post('/api/jobs', payload);
    return data;
  }

  async getJob(jobId: string) {
    const { data } = await this.http.get(`/api/jobs/${jobId}`);
    return data;
  }

  async listJobs(userId: number, limit: number, cursor: string | number = 0) {
    const { data } = await this.http.get('/api/jobs', {
      params: { user_id: userId, limit, cursor },
    });
    return data;
  }
}
