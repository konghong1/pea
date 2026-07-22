import { Module } from '@nestjs/common';
import { CanvasesService } from './canvases.service';
import { CanvasesController } from './canvases.controller';

@Module({
  controllers: [CanvasesController],
  providers: [CanvasesService],
  exports: [CanvasesService],
})
export class CanvasesModule {}
