import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';
import { HttpExceptionFilter } from './common/filters/http-exception.filter';
import { installEgressProxyFromEnv } from './common/proxy/bootstrap-proxy';

async function bootstrap() {
  // 必须在监听端口前完成: ① 代理可达 => 覆盖 globalThis.fetch 走代理;
  // ② 代理不可达 => 清除 HTTP(S)_PROXY env, 防止 axios 读到死代理导致
  //   所有出网请求 ECONNREFUSED (fetch-models 报 172.17.0.1:33210 的根因之一)。
  // await 保证首个请求到达时代理策略已定型, 无竞态。
  await installEgressProxyFromEnv();
  const app = await NestFactory.create(AppModule);
  app.useGlobalFilters(new HttpExceptionFilter());
  app.useGlobalPipes(
    new ValidationPipe({ whitelist: true, transform: true, forbidNonWhitelisted: false }),
  );
  app.enableCors({ origin: '*' });
  const port = Number(process.env.PEA_PORT ?? 4000);
  await app.listen(port);
  // eslint-disable-next-line no-console
  console.log(`pea BFF listening on :${port}`);
}
bootstrap();
