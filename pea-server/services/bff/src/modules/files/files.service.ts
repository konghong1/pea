import { Injectable, BadRequestException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as Minio from 'minio';

/** 文件存储 (ARCH D8 / T-FILE-01~04): 预签名直传 + 强制签名访问防跨用户泄露. */
@Injectable()
export class FilesService {
  private client: Minio.Client;
  private bucket: string;
  private cdnBase: string;

  constructor(config: ConfigService) {
    const m = config.get('minio');
    this.bucket = m.bucket;
    this.cdnBase = m.cdnBaseUrl;
    this.client = new Minio.Client({
      endPoint: m.endPoint,
      port: m.port,
      useSSL: m.useSSL,
      accessKey: m.accessKey,
      secretKey: m.secretKey,
    });
  }

  async ensureBucket() {
    const exists = await this.client.bucketExists(this.bucket);
    if (!exists) await this.client.makeBucket(this.bucket);
  }

  /** 用户资源命名空间前缀: 所有用户文件必须位于 u:<userId>/ 下 (防跨用户访问). */
  private userPrefix(userId: number): string {
    return `u:${userId}/`;
  }

  /** 生成 PUT 预签名 URL (前端直传, 省 BFF 带宽). key 必须位于调用者的命名空间内. */
  async presignPut(key: string, userId: number, expiresSec = 600): Promise<string> {
    const prefix = this.userPrefix(userId);
    if (!key || key.includes('..') || !key.startsWith(prefix)) {
      throw new BadRequestException(`invalid key: must be under ${prefix}`);
    }
    return this.client.presignedPutObject(this.bucket, key, expiresSec);
  }

  /** 生成 GET 签名 URL (强制签名访问, 防未授权外泄). 仅允许访问调用者自己的资源. */
  async presignGet(key: string, userId: number, expiresSec = 3600): Promise<string> {
    const prefix = this.userPrefix(userId);
    if (!key || !key.startsWith(prefix)) {
      throw new BadRequestException('forbidden: key does not belong to user');
    }
    return this.client.presignedGetObject(this.bucket, key, expiresSec);
  }

  /** 公开 CDN URL (仅适合已配置公开策略的资源; 默认走签名访问). */
  publicUrl(key: string): string {
    return `${this.cdnBase}/${key}`;
  }

  async remove(key: string, userId: number) {
    const prefix = this.userPrefix(userId);
    if (!key || !key.startsWith(prefix)) {
      throw new BadRequestException('forbidden: key does not belong to user');
    }
    return this.client.removeObject(this.bucket, key);
  }
}
