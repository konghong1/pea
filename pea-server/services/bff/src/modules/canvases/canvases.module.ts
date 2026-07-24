import { Module } from '@nestjs/common';
import { CanvasesService } from './canvases.service';
import { CanvasesController, SharedCanvasController } from './canvases.controller';

@Module({
  controllers: [CanvasesController, SharedCanvasController],
  providers: [CanvasesService],
  exports: [CanvasesService],
})
export class CanvasesModule {}