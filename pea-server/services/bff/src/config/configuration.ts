/** 集中读取环境变量 (12-factor). 被 ConfigModule 加载. */
export default () => {
  // 安全红线: 生产环境必须由环境变量注入密钥, 缺失即启动失败 (fail-fast).
  // 本地/开发缺省时退化为显式不安全默认值并在日志可见, 但绝不可用于生产.
  const jwtSecret = process.env.PEA_JWT_SECRET;
  if (!jwtSecret && process.env.NODE_ENV === 'production') {
    throw new Error('[config] PEA_JWT_SECRET must be set in production');
  }
  const internalToken = process.env.PEA_INTERNAL_SERVICE_TOKEN;
  if (!internalToken && process.env.NODE_ENV === 'production') {
    throw new Error('[config] PEA_INTERNAL_SERVICE_TOKEN must be set in production');
  }

  return {
    port: parseInt(process.env.PEA_PORT ?? '4000', 10),
    jwt: {
      secret: jwtSecret ?? 'dev-insecure-secret-do-not-use-in-prod',
      expiresIn: process.env.PEA_JWT_EXPIRES_IN ?? '7d',
    },
    db: {
      host: process.env.PEA_DB_HOST ?? 'mysql',
      port: parseInt(process.env.PEA_DB_PORT ?? '3306', 10),
      user: process.env.PEA_DB_USER ?? 'pea',
      password: process.env.PEA_DB_PASSWORD ?? 'pea_dev',
      database: process.env.PEA_DB_NAME ?? 'pea',
    },
    redis: {
      url: process.env.PEA_REDIS_URL ?? 'redis://redis:6379/0',
    },
    minio: {
      endPoint: (process.env.PEA_MINIO_ENDPOINT ?? 'minio:9000').split(':')[0],
      port: parseInt((process.env.PEA_MINIO_ENDPOINT ?? 'minio:9000').split(':')[1] ?? '9000', 10),
      useSSL: (process.env.PEA_MINIO_USE_SSL ?? 'false') === 'true',
      accessKey: process.env.PEA_MINIO_ACCESS_KEY ?? 'minioadmin',
      secretKey: process.env.PEA_MINIO_SECRET_KEY ?? 'minioadmin',
      bucket: process.env.PEA_MINIO_BUCKET ?? 'pea-media',
      cdnBaseUrl: process.env.PEA_CDN_BASE_URL ?? 'http://localhost:9000/pea-media',
      // 预签名 URL 返回给浏览器时使用的可达 host（dev 下 minio:9000 容器别名浏览器不可达，需改 localhost:9000）。
      publicEndpoint: process.env.PEA_MINIO_PUBLIC_ENDPOINT ?? (process.env.PEA_MINIO_ENDPOINT ?? 'minio:9000'),
    },
    orchestratorUrl: process.env.PEA_ORCHESTRATOR_URL ?? 'http://generation-orchestrator:8000',
    internalToken: internalToken ?? 'dev-insecure-token-do-not-use-in-prod',
    freeTapies: parseInt(process.env.PEA_FREE_TAPIES ?? '1000', 10),
    rateLimitPerMin: parseInt(process.env.PEA_RATE_LIMIT_PER_MIN ?? '120', 10),
  };
};
