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
      expiresIn: process.env.PEA_JWT_EXPIRES_IN ?? '30d',
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
    // 管理员账户 (启动时由 AuthService 幂等同步到 users 表):
    // - PEA_ADMIN_PASSWORD 设置后, 每次启动都会把该账户密码重置为此值 (bcrypt 加密后入库),
    //   即"密码以环境变量为准"; 未设置则不动库里已有密码 (沿用 SQL 种子)。
    admin: {
      email: process.env.PEA_ADMIN_EMAIL ?? 'admin@pea.ai',
      password: process.env.PEA_ADMIN_PASSWORD ?? '',
    },
    orchestratorUrl: process.env.PEA_ORCHESTRATOR_URL ?? 'http://generation-orchestrator:8000',
    internalToken: internalToken ?? 'dev-insecure-token-do-not-use-in-prod',
    freeTapies: parseInt(process.env.PEA_FREE_TAPIES ?? '1000', 10),
    rateLimitPerMin: parseInt(process.env.PEA_RATE_LIMIT_PER_MIN ?? '120', 10),
    /**
     * 是否允许用户「自助购买套餐」直接到账（POST /plans/purchase）。
     *
     * ⚠️ 安全默认关闭。该接口无任何支付校验，开启后任意登录用户可无限调用，
     * 白嫖 Tapies 并把自己提升到任意 plan_level（自己给自己续费）。
     * 仅在无外部用户的内网演示环境可临时设为 1；线上必须保持 0，
     * 走「下单 → 扫收款码付款 → 管理员确认到账 → 发放权益」流程。
     */
    allowSelfPurchase: (process.env.PEA_ALLOW_SELF_PURCHASE ?? '0') === '1',
    /**
     * 支付通道。三条路径共用同一张订单表、同一套状态机、同一个发放函数，
     * 切换只需改一个环境变量，无需数据迁移或代码重构。
     *
     *  - manual_qr      个人收款码 + 管理员确认到账（默认，无需商户资质，立即可用）
     *  - wechat_native  微信支付 Native 扫码 + 回调自动发放（需商户号，填 wechat.*）
     *  - codepay        通用码支付/聚合支付网关 + 回调自动发放（个人可接，无需执照；
     *                   默认按易支付 Epay 协议实现，字段/签名/回调全走环境变量，
     *                   选定服务商后只填配置不改代码）
     */
    payment: {
      provider: (process.env.PEA_PAY_PROVIDER ?? 'manual_qr') as 'manual_qr' | 'wechat_native' | 'codepay',
      /** 订单支付有效期（分钟）。超时未付自动置 expired，释放金额尾数。 */
      orderTtlMinutes: parseInt(process.env.PEA_ORDER_TTL_MINUTES ?? '30', 10),
      /**
       * 是否给应付金额追加随机分位尾数（0~99 分）。
       * 个人收款码收不到「谁付了多少」的回调，靠唯一尾数把收款通知一一对应到订单，
       * 避免同价并发订单撞单。走有回调的通道（wechat_native/codepay）后此项无意义，可关闭。
       */
      amountFingerprint: (process.env.PEA_PAY_AMOUNT_FINGERPRINT ?? '1') === '1',
      /** 对外可达基址，用于拼接支付回调地址（codepay 用；wechat 走自己的 notifyUrl）。 */
      publicBaseUrl: process.env.PEA_PUBLIC_BASE_URL ?? '',
      wechat: {
        appId: process.env.PEA_WXPAY_APPID ?? '',
        mchId: process.env.PEA_WXPAY_MCHID ?? '',
        apiV3Key: process.env.PEA_WXPAY_API_V3_KEY ?? '',
        serialNo: process.env.PEA_WXPAY_SERIAL_NO ?? '',
        privateKey: process.env.PEA_WXPAY_PRIVATE_KEY ?? '',
        notifyUrl: process.env.PEA_WXPAY_NOTIFY_URL ?? '',
      },
      /**
       * 通用码支付/聚合支付网关配置（默认 Epay 协议，参数全可配）。
       * 个人收款码无服务器回调，码支付服务商是折中：把你的个人码包一层，
       * 它收到款后回调 /pay/notify/codepay，你按签名验真后自动发放，全程零人工。
       * 各家字段名/签名算法不同，这里一律走环境变量，未定服务商也能先编译部署。
       */
      codepay: {
        gatewayUrl: process.env.PEA_CODEPAY_GATEWAY_URL ?? '',
        pid: process.env.PEA_CODEPAY_PID ?? '',
        key: process.env.PEA_CODEPAY_KEY ?? '',
        createPath: process.env.PEA_CODEPAY_CREATE_PATH ?? '/mapi/order/submit',
        signAlgo: (process.env.PEA_CODEPAY_SIGN_ALGO ?? 'md5') as 'md5' | 'hmac-md5',
        /** 签名串拼接风格：direct=排序串后直接拼密钥；saltparam=排序串&salt=密钥。 */
        signStyle: (process.env.PEA_CODEPAY_SIGN_STYLE ?? 'direct') as 'direct' | 'saltparam',
        signField: process.env.PEA_CODEPAY_SIGN_FIELD ?? 'sign',
        fieldOrder: process.env.PEA_CODEPAY_FIELD_ORDER ?? 'out_trade_no',
        fieldMoney: process.env.PEA_CODEPAY_FIELD_MONEY ?? 'money',
        fieldTradeNo: process.env.PEA_CODEPAY_FIELD_TRADE_NO ?? 'trade_no',
        reqPid: process.env.PEA_CODEPAY_REQ_PID ?? 'pid',
        reqOutTradeNo: process.env.PEA_CODEPAY_REQ_OUT_TRADE_NO ?? 'out_trade_no',
        reqName: process.env.PEA_CODEPAY_REQ_NAME ?? 'name',
        reqMoney: process.env.PEA_CODEPAY_REQ_MONEY ?? 'money',
        reqNotify: process.env.PEA_CODEPAY_REQ_NOTIFY ?? 'notify_url',
        reqReturn: process.env.PEA_CODEPAY_REQ_RETURN ?? 'return_url',
        reqTypeField: process.env.PEA_CODEPAY_REQ_TYPE_FIELD ?? 'type',
        reqTypeValue: process.env.PEA_CODEPAY_REQ_TYPE_VALUE ?? 'json',
        signTypeField: process.env.PEA_CODEPAY_SIGN_TYPE_FIELD ?? 'sign_type',
        signTypeValue: process.env.PEA_CODEPAY_SIGN_TYPE_VALUE ?? 'MD5',
        respQr: process.env.PEA_CODEPAY_RESP_QR ?? 'qrcode',
        respPayUrl: process.env.PEA_CODEPAY_RESP_PAY_URL ?? 'pay_url',
        moneyUnit: (process.env.PEA_CODEPAY_MONEY_UNIT ?? 'yuan') as 'yuan' | 'cent',
      },
    },
  };
};
