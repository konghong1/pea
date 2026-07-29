import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';
import { HttpExceptionFilter } from './common/filters/http-exception.filter';
import { installEgressProxyFromEnv } from './common/proxy/bootstrap-proxy';

// 必须尽早执行: 覆盖 globalThis.fetch, 让后续所有出网请求(含 Node 内置 undici)走代理。
installEgressProxyFromEnv();

async function bootstrap() {
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
