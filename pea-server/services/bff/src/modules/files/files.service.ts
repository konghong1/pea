import { Injectable, BadRequestException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as Minio from 'minio';

/** 文件存储 (ARCH D8 / T-FILE-01~04): 预签名直传 + 强制签名访问防跨用户泄露. */
@Injectable()
export class FilesService {
  private client: Minio.Client;
  private bucket: string;
  private cdnBase: string;
  private internalHostPort: string;
  private publicHostPort: string;

  constructor(config: ConfigService) {
    const m = config.get('minio');
    this.bucket = m.bucket;
    this.cdnBase = m.cdnBaseUrl;
    this.internalHostPort = `${m.endPoint}:${m.port}`;
    this.publicHostPort = m.publicEndpoint ?? this.internalHostPort;
    this.client = new Minio.Client({
      endPoint: m.endPoint,
      port: m.port,
      useSSL: m.useSSL,
      accessKey: m.accessKey,
      secretKey: m.secretKey,
    });
  }

  /** 预签名 URL 默认用内部 endPoint（容器别名），浏览器不可达；改写为外部可达 host。 */
  private toPublic(url: string): string {
    if (this.publicHostPort === this.internalHostPort) return url;
    return url.replace(this.internalHostPort, this.publicHostPort);
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
    return this.toPublic(await this.client.presignedPutObject(this.bucket, key, expiresSec));
  }

  /** 生成 GET 签名 URL (强制签名访问, 防未授权外泄). 仅允许访问调用者自己的资源. */
  async presignGet(key: string, userId: number, expiresSec = 3600): Promise<string> {
    const prefix = this.userPrefix(userId);
    if (!key || !key.startsWith(prefix)) {
      throw new BadRequestException('forbidden: key does not belong to user');
    }
    return this.toPublic(await this.client.presignedGetObject(this.bucket, key, expiresSec));
  }

  /** 服务端直写对象（供前端经 BFF 代理上传，避免预签名 URL 的 host 绑定/跨域问题）。 */
  async putObject(key: string, body: Buffer, contentType?: string): Promise<void> {
    if (!key || key.includes('..')) throw new BadRequestException('invalid key');
    await this.client.putObject(this.bucket, key, body, undefined, {
      'Content-Type': contentType || 'application/octet-stream',
    });
  }

  /** 取对象可读流（供 BFF 代理下载，同域返回，规避预签名 host 问题）。 */
  async getObjectStream(key: string): Promise<NodeJS.ReadableStream> {
    return (await this.client.getObject(this.bucket, key)) as NodeJS.ReadableStream;
  }

  /** 取对象元信息（含 contentType）。 */
  async statObject(key: string) {
    return await this.client.statObject(this.bucket, key);
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
