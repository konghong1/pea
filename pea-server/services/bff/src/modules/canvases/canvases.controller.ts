import {
  Body,
  Controller,
  Get,
  Param,
  Post,
  Put,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { CanvasesService } from './canvases.service';
import { CreateCanvasDto, SaveCanvasDto } from './canvases.dto';

@Controller('canvases')
@UseGuards(JwtAuthGuard)
export class CanvasesController {
  constructor(private readonly canvases: CanvasesService) {}

  @Post()
  create(@CurrentUser() u: { sub: number }, @Body() dto: CreateCanvasDto) {
    return this.canvases.create(u.sub, dto.title);
  }

  @Put(':id')
  save(
    @CurrentUser() u: { sub: number },
    @Param('id') id: string,
    @Body() dto: SaveCanvasDto,
  ) {
    return this.canvases.save(u.sub, Number(id), dto.graph_json, dto.version);
  }

  @Get(':id')
  get(@CurrentUser() u: { sub: number }, @Param('id') id: string) {
    return this.canvases.get(u.sub, Number(id));
  }
}
