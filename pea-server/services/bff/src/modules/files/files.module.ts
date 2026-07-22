import { Module, OnModuleInit } from '@nestjs/common';
import { FilesService } from './files.service';
import { FilesController } from './files.controller';

@Module({
  controllers: [FilesController],
  providers: [FilesService],
  exports: [FilesService],
})
export class FilesModule implements OnModuleInit {
  constructor(private readonly files: FilesService) {}
  async onModuleInit() {
    try {
      await this.files.ensureBucket();
    } catch (e) {
      // minio 可能尚未就绪: 不阻断启动, presign 时再失败并由调用方处理
      console.warn('[files] ensureBucket deferred:', (e as Error).message);
    }
  }
}
