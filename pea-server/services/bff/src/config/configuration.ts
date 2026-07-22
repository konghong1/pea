/** 集中读取环境变量 (12-factor). 被 ConfigModule 加载. */
export default () => ({
  port: parseInt(process.env.PEA_PORT ?? '4000', 10),
  jwt: {
    secret: process.env.PEA_JWT_SECRET ?? 'change-me-in-prod',
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
  },
  orchestratorUrl: process.env.PEA_ORCHESTRATOR_URL ?? 'http://generation-orchestrator:8000',
  internalToken: process.env.PEA_INTERNAL_SERVICE_TOKEN ?? 'change-me-in-prod',
  freeTapies: parseInt(process.env.PEA_FREE_TAPIES ?? '1000', 10),
  rateLimitPerMin: parseInt(process.env.PEA_RATE_LIMIT_PER_MIN ?? '120', 10),
});
