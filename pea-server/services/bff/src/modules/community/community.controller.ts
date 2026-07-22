import {
  Controller,
  Get,
  Post,
  Delete,
  Param,
  Body,
  Query,
  UseGuards,
  ParseIntPipe,
} from '@nestjs/common';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { CurrentUser } from '../../common/decorators/current-user.decorator';
import { CommunityService } from './community.service';
import { CreateWorkDto, CommentDto } from './community.dto';

interface AuthPayload {
  sub: number;
}

@Controller('works')
@UseGuards(JwtAuthGuard)
export class CommunityController {
  constructor(private readonly community: CommunityService) {}

  /** T-M4-01 社区 feed */
  @Get()
  feed(@CurrentUser() user: AuthPayload, @Query('limit') limit?: string) {
    const n = limit ? Math.min(parseInt(limit, 10) || 20, 50) : 20;
    return this.community.feed(user.sub, n);
  }

  /** T-M4-01 发布作品 */
  @Post()
  create(@CurrentUser() user: AuthPayload, @Body() dto: CreateWorkDto) {
    return this.community.create(user.sub, dto.caption, dto.mediaUrls ?? []);
  }

  /** T-M4-02 作品详情 */
  @Get(':id')
  detail(@CurrentUser() user: AuthPayload, @Param('id', ParseIntPipe) id: number) {
    return this.community.detail(user.sub, id);
  }

  /** T-M4-02 点赞 */
  @Post(':id/like')
  like(@CurrentUser() user: AuthPayload, @Param('id', ParseIntPipe) id: number) {
    return this.community.like(user.sub, id);
  }

  @Delete(':id/like')
  unlike(@CurrentUser() user: AuthPayload, @Param('id', ParseIntPipe) id: number) {
    return this.community.unlike(user.sub, id);
  }

  /** T-M4-02 收藏 */
  @Post(':id/favorite')
  favorite(@CurrentUser() user: AuthPayload, @Param('id', ParseIntPipe) id: number) {
    return this.community.favorite(user.sub, id);
  }

  @Delete(':id/favorite')
  unfavorite(@CurrentUser() user: AuthPayload, @Param('id', ParseIntPipe) id: number) {
    return this.community.unfavorite(user.sub, id);
  }

  /** T-M4-02 评论列表 */
  @Get(':id/comments')
  comments(@Param('id', ParseIntPipe) id: number) {
    return this.community.comments(id);
  }

  /** T-M4-02 发评论 */
  @Post(':id/comments')
  addComment(
    @CurrentUser() user: AuthPayload,
    @Param('id', ParseIntPipe) id: number,
    @Body() dto: CommentDto,
  ) {
    return this.community.addComment(user.sub, id, dto.content);
  }
}
