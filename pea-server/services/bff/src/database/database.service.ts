import {
  Injectable,
  OnModuleInit,
  OnModuleDestroy,
  InternalServerErrorException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import mysql, { Pool, PoolConnection, RowDataPacket, OkPacket } from 'mysql2/promise';

export type QueryResult = RowDataPacket[] | OkPacket | RowDataPacket[][];

/**
 * MySQL 连接池 (mysql2/promise). 所有模块通过它访问自己拥有的表,
 * 禁止跨模块直连他域表 (ARCH §6 模块依赖方向).
 */
@Injectable()
export class DatabaseService implements OnModuleInit, OnModuleDestroy {
  private pool!: Pool;

  constructor(private readonly config: ConfigService) {}

  onModuleInit() {
    const db = this.config.get('db');
    this.pool = mysql.createPool({
      host: db.host,
      port: db.port,
      user: db.user,
      password: db.password,
      database: db.database,
      waitForConnections: true,
      connectionLimit: 10,
      charset: 'utf8mb4',
    });
  }

  onModuleDestroy() {
    return this.pool?.end();
  }

  getPool(): Pool {
    return this.pool;
  }

  /** 执行查询 */
  async query<T = any>(sql: string, params: any[] = []): Promise<T> {
    try {
      const [rows] = await this.pool.query(sql, params);
      return rows as T;
    } catch (e) {
      // 生产环境不暴露数据库错误细节，防止信息泄露
      const isProd = process.env.NODE_ENV === 'production';
      const message = isProd
        ? 'database error'
        : `DB error: ${(e as Error).message}`;
      throw new InternalServerErrorException(message);
    }
  }

  /** 事务: 回调内拿到连接, 自动 commit/rollback */
  async transaction<T>(fn: (conn: PoolConnection) => Promise<T>): Promise<T> {
    const conn = await this.pool.getConnection();
    await conn.beginTransaction();
    try {
      const r = await fn(conn);
      await conn.commit();
      return r;
    } catch (e) {
      await conn.rollback();
      throw e;
    } finally {
      conn.release();
    }
  }
}
