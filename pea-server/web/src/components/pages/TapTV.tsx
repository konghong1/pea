import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Modal,
  Input,
  Drawer,
  Avatar,
  Empty,
  Skeleton,
  Tooltip,
  App,
} from 'antd';
import {
  PlusOutlined,
  HeartOutlined,
  HeartFilled,
  StarOutlined,
  StarFilled,
  MessageOutlined,
  SendOutlined,
  PlayCircleFilled,
} from '@ant-design/icons';
import { api } from '../../api/client';
import { useAuth } from '../../store/auth';
import { toast } from '../../store/toast';

interface Work {
  id: number;
  user_id: number;
  media_urls: string | null | unknown[];
  caption: string;
  created_at: string;
  likes_count: number;
  comments_count: number;
  favorites_count: number;
  display_name: string;
  liked_by_me: number;
  favorited_by_me: number;
}

interface Comment {
  id: number;
  work_id: number;
  user_id: number;
  content: string;
  created_at: string;
  display_name: string;
}

/** 根据 id 生成稳定的渐变色（媒体缺失时作占位，避免外链依赖）。 */
const GRADIENTS = [
  'linear-gradient(135deg,#8b5cf6,#1fa2dc)',
  'linear-gradient(135deg,#fd79a8,#a29bfe)',
  'linear-gradient(135deg,#fdcb6e,#e17055)',
  'linear-gradient(135deg,#1fa2dc,#8b5cf6)',
  'linear-gradient(135deg,#34d399,#1fa2dc)',
];
const gradFor = (id: number) => GRADIENTS[id % GRADIENTS.length];

/** 媒体占位标签: 兼容 JSON 列已解析为数组 / 字符串 / null 三种形态。 */
const hasMedia = (m: unknown): boolean => {
  if (Array.isArray(m)) return m.length > 0;
  if (typeof m === 'string') {
    if (!m) return false;
    try {
      return JSON.parse(m).length > 0;
    } catch {
      return false;
    }
  }
  return false;
};

function timeAgo(iso: string): string {
  const d = new Date(iso).getTime();
  const s = Math.max(1, Math.floor((Date.now() - d) / 1000));
  if (s < 60) return `${s}秒前`;
  if (s < 3600) return `${Math.floor(s / 60)}分钟前`;
  if (s < 86400) return `${Math.floor(s / 3600)}小时前`;
  return `${Math.floor(s / 86400)}天前`;
}

function WorkCard({
  w,
  onOpen,
  onLike,
  onFav,
}: {
  w: Work;
  onOpen: () => void;
  onLike: () => void;
  onFav: () => void;
}) {
  const liked = w.liked_by_me === 1;
  const faved = w.favorited_by_me === 1;
  return (
    <div className="pea-card group flex flex-col overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:shadow-xl">
      <button
        onClick={onOpen}
        className="relative block h-40 w-full overflow-hidden"
        style={{ background: gradFor(w.id) }}
        aria-label="查看作品"
      >
        <span className="absolute inset-0 flex items-center justify-center text-4xl text-white/90">
          <PlayCircleFilled />
        </span>
        <span className="absolute bottom-2 right-2 rounded-full bg-black/35 px-2 py-0.5 text-[11px] text-white backdrop-blur">
          {hasMedia(w.media_urls) ? '视频' : '图文'}
        </span>
      </button>
      <div className="flex flex-1 flex-col p-3">
        <p className="line-clamp-2 text-sm text-gray-800 dark:text-gray-100">{w.caption}</p>
        <div className="mt-2 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          <Avatar size={20} style={{ background: gradFor(w.id) }}>
            {w.display_name.slice(0, 1)}
          </Avatar>
          <span className="font-medium text-gray-700 dark:text-gray-200">{w.display_name}</span>
          <span>· {timeAgo(w.created_at)}</span>
        </div>
        <div className="mt-3 flex items-center gap-1 border-t border-black/5 pt-2 dark:border-white/10">
          <Tooltip title={liked ? '取消点赞' : '点赞'}>
            <button
              onClick={onLike}
              aria-label={liked ? '取消点赞' : '点赞'}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-sm transition-colors ${
                liked ? 'text-rose-500' : 'text-gray-500 hover:text-rose-500 dark:text-gray-400'
              }`}
            >
              {liked ? <HeartFilled /> : <HeartOutlined />}
              {w.likes_count}
            </button>
          </Tooltip>
          <Tooltip title={faved ? '取消收藏' : '收藏'}>
            <button
              onClick={onFav}
              aria-label={faved ? '取消收藏' : '收藏'}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-sm transition-colors ${
                faved ? 'text-amber-500' : 'text-gray-500 hover:text-amber-500 dark:text-gray-400'
              }`}
            >
              {faved ? <StarFilled /> : <StarOutlined />}
              {w.favorites_count}
            </button>
          </Tooltip>
          <button
            onClick={onOpen}
            className="ml-auto flex items-center gap-1 rounded-md px-2 py-1 text-sm text-gray-500 hover:text-pea-brand dark:text-gray-400"
          >
            <MessageOutlined />
            {w.comments_count}
          </button>
        </div>
      </div>
    </div>
  );
}

/** M4 TapTV 社区 (T-M4-01/02): feed、发布、点赞、收藏、评论。 */
export default function TapTV() {
  const { message } = App.useApp();
  const { user } = useAuth();
  const [works, setWorks] = useState<Work[]>([]);
  const [loading, setLoading] = useState(true);
  const [publishOpen, setPublishOpen] = useState(false);
  const [caption, setCaption] = useState('');
  const [mediaInput, setMediaInput] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [detail, setDetail] = useState<Work | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [commentText, setCommentText] = useState('');

  const loadFeed = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Work[]>('/works');
      setWorks(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  const openDetail = useCallback(async (w: Work) => {
    setDetail(w);
    try {
      const { data } = await api.get<Comment[]>(`/works/${w.id}/comments`);
      setComments(data);
    } catch {
      setComments([]);
    }
  }, []);

  const toggleLike = useCallback(
    async (w: Work) => {
      try {
        if (w.liked_by_me === 1) await api.delete(`/works/${w.id}/like`);
        else await api.post(`/works/${w.id}/like`);
        const patch = (cur: Work[]) =>
          cur.map((x) =>
            x.id === w.id
              ? {
                  ...x,
                  liked_by_me: x.liked_by_me === 1 ? 0 : 1,
                  likes_count: x.likes_count + (x.liked_by_me === 1 ? -1 : 1),
                }
              : x,
          );
        setWorks(patch);
        setDetail((d) => (d && d.id === w.id ? patch([d])[0] : d));
      } catch {
        toast.error('操作失败，请重试');
      }
    },
    [],
  );

  const toggleFav = useCallback(
    async (w: Work) => {
      try {
        if (w.favorited_by_me === 1) await api.delete(`/works/${w.id}/favorite`);
        else await api.post(`/works/${w.id}/favorite`);
        const patch = (cur: Work[]) =>
          cur.map((x) =>
            x.id === w.id
              ? {
                  ...x,
                  favorited_by_me: x.favorited_by_me === 1 ? 0 : 1,
                  favorites_count: x.favorites_count + (x.favorited_by_me === 1 ? -1 : 1),
                }
              : x,
          );
        setWorks(patch);
        setDetail((d) => (d && d.id === w.id ? patch([d])[0] : d));
      } catch {
        toast.error('操作失败，请重试');
      }
    },
    [],
  );

  const submitPublish = useCallback(async () => {
    if (!caption.trim()) {
      message.warning('写点什么再发布吧');
      return;
    }
    setSubmitting(true);
    try {
      const urls = mediaInput
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      await api.post('/works', { caption: caption.trim(), mediaUrls: urls });
      setPublishOpen(false);
      setCaption('');
      setMediaInput('');
      toast.success('发布成功 🎉');
      loadFeed();
    } catch {
      toast.error('发布失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }, [caption, mediaInput, loadFeed, message]);

  const submitComment = useCallback(async () => {
    if (!detail || !commentText.trim()) return;
    try {
      await api.post(`/works/${detail.id}/comments`, { content: commentText.trim() });
      setCommentText('');
      const { data } = await api.get<Comment[]>(`/works/${detail.id}/comments`);
      setComments(data);
      setWorks((cur) =>
        cur.map((x) => (x.id === detail.id ? { ...x, comments_count: x.comments_count + 1 } : x)),
      );
      setDetail((d) => (d ? { ...d, comments_count: d.comments_count + 1 } : d));
    } catch {
      toast.error('评论失败，请重试');
    }
  }, [detail, commentText]);

  return (
    <div className="pea-page">
      <div className="pea-page-pad" style={{ maxWidth: 1180 }}>
        <div className="flex items-end justify-between">
          <div>
            <div className="pea-hero-title">探索 TapTV</div>
            <p className="pea-muted" style={{ marginTop: 8 }}>
              查看创作者们的完整过程 —— 从想法到成片。
            </p>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setPublishOpen(true)}>
            发布作品
          </Button>
        </div>

        {loading ? (
          <div className="pea-card-grid">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="pea-card">
                <Skeleton active paragraph={{ rows: 2 }} />
              </div>
            ))}
          </div>
        ) : works.length === 0 ? (
          <div style={{ marginTop: 40 }}>
            <Empty description="还没有作品，来发布第一个吧" />
          </div>
        ) : (
          <div className="pea-card-grid">
            {works.map((w) => (
              <WorkCard
                key={w.id}
                w={w}
                onOpen={() => openDetail(w)}
                onLike={() => toggleLike(w)}
                onFav={() => toggleFav(w)}
              />
            ))}
          </div>
        )}
      </div>

      {/* 发布弹窗 */}
      <Modal
        title="发布作品"
        open={publishOpen}
        onCancel={() => setPublishOpen(false)}
        onOk={submitPublish}
        okText="发布"
        confirmLoading={submitting}
        destroyOnClose
      >
        <Input.TextArea
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          placeholder="分享你的创作过程、心得或成片……"
          rows={4}
          maxLength={2000}
          showCount
        />
        <div style={{ marginTop: 12 }}>
          <div className="pea-muted" style={{ fontSize: 12, marginBottom: 4 }}>
            媒体链接（可选，每行一个 URL；留空将显示渐变占位）
          </div>
          <Input.TextArea
            value={mediaInput}
            onChange={(e) => setMediaInput(e.target.value)}
            placeholder="https://..."
            rows={2}
          />
        </div>
      </Modal>

      {/* 作品详情 + 评论 */}
      <Drawer
        title="作品详情"
        placement="right"
        width={420}
        open={!!detail}
        onClose={() => setDetail(null)}
        destroyOnClose
      >
        {detail && (
          <div>
            <div
              className="mb-3 flex h-48 w-full items-center justify-center rounded-xl text-5xl text-white/90"
              style={{ background: gradFor(detail.id) }}
            >
              <PlayCircleFilled />
            </div>
            <div className="mb-2 flex items-center gap-2">
              <Avatar style={{ background: gradFor(detail.id) }}>
                {detail.display_name.slice(0, 1)}
              </Avatar>
              <div>
                <div className="text-sm font-medium">{detail.display_name}</div>
                <div className="text-xs text-gray-400">{timeAgo(detail.created_at)}</div>
              </div>
            </div>
            <p className="mb-3 text-sm text-gray-800 dark:text-gray-100">{detail.caption}</p>

            <div className="mb-4 flex items-center gap-2">
              <Button
                icon={detail.liked_by_me === 1 ? <HeartFilled /> : <HeartOutlined />}
                type={detail.liked_by_me === 1 ? 'primary' : 'default'}
                danger={detail.liked_by_me === 1}
                aria-label="点赞"
                onClick={() => toggleLike(detail)}
              >
                {detail.likes_count}
              </Button>
              <Button
                icon={detail.favorited_by_me === 1 ? <StarFilled /> : <StarOutlined />}
                type={detail.favorited_by_me === 1 ? 'primary' : 'default'}
                aria-label="收藏"
                onClick={() => toggleFav(detail)}
              >
                {detail.favorites_count}
              </Button>
            </div>

            <div className="mb-2 text-sm font-semibold">评论 ({comments.length})</div>
            <div className="flex flex-col gap-2">
              {comments.length === 0 && (
                <div className="pea-muted" style={{ fontSize: 13 }}>
                  还没有评论，来抢沙发
                </div>
              )}
              {comments.map((c) => (
                <div key={c.id} className="rounded-lg bg-black/5 p-2 text-sm dark:bg-white/5">
                  <div className="font-medium text-gray-700 dark:text-gray-200">
                    {c.display_name}
                    <span className="ml-2 text-xs font-normal text-gray-400">
                      {timeAgo(c.created_at)}
                    </span>
                  </div>
                  <div className="mt-0.5 text-gray-800 dark:text-gray-100">{c.content}</div>
                </div>
              ))}
            </div>

            <div className="mt-3 flex items-center gap-2">
              <Input
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                placeholder="说点什么……"
                onPressEnter={submitComment}
                disabled={!user}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                aria-label="发送评论"
                onClick={submitComment}
                disabled={!commentText.trim()}
              />
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
