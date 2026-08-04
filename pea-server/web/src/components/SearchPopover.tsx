import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Input } from 'antd';
import {
  AppstoreOutlined,
  FileImageOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  SoundOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import NodeIcon from './NodeIcon';
import { useCanvas, PeaNodeData } from '../store/canvas';
import { getFileUrl } from '../api/files';

/**
 * 画布内统一搜索弹层（对齐 PRD 参考图 / Visily 风格）。
 *
 * 设计要点：
 * - Portal 渲染到 body，避免 ReactFlow 父容器 z-index/transform 影响；
 * - 中央浮层 + 全屏透明 backdrop，点击外区域自动关闭；
 * - 类别筛选（全部 / 图片 / 视频 / 文本 / 音频 / World / 分组），自然换行无横滚条；
 * - 同时匹配 label 与 prompt（按关键词 + 类型过滤）；
 * - 命中点击：select + setViewport 居中视口到目标节点；
 * - 键盘：↑↓ 上下移动，Enter 命中，Esc 关闭；
 * - 缩略图覆盖：resultUrl / resultUrls[idx] / url / fileKey(异步签名)；
 * - 视频节点用 <video preload="metadata"> 取首帧；纯图片直接 <img>。
 */
export default function SearchPopover({ onClose }: { onClose: () => void }) {
  const nodes = useCanvas((s) => s.nodes);
  const select = useCanvas((s) => s.select);

  // 类型筛选："all" | "group" | PeaNodeKind
  const [filter, setFilter] = useState<'all' | 'group' | string>('all');
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<any>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // 自动 focus 输入框（弹层一打开就能打字）
  useEffect(() => {
    const t = window.setTimeout(() => {
      try {
        inputRef.current?.focus?.({ cursor: 'all' });
      } catch {
        inputRef.current?.focus?.();
      }
    }, 30);
    return () => window.clearTimeout(t);
  }, []);

  // Esc 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  // 过滤 & 匹配
  const matched = useMemo(() => {
    const q = query.trim().toLowerCase();
    return nodes.filter((n) => {
      // 类型筛选：group 是 ReactFlow 的节点 type 而不是 data.kind
      if (filter === 'group') {
        if ((n.type ?? 'pea') !== 'group') return false;
      } else if (filter !== 'all') {
        if (n.data.kind !== filter) return false;
      }
      if (!q) return true;
      const label = (n.data.label ?? '').toLowerCase();
      const prompt = (n.data.prompt ?? '').toLowerCase();
      const html = (n.data.html ?? '').toLowerCase();
      return label.includes(q) || prompt.includes(q) || html.includes(q);
    });
  }, [nodes, query, filter]);

  // query 或 filter 变化时把 active 拉回 0，避免越界
  useEffect(() => {
    setActive(0);
  }, [query, filter]);

  // 滚动跟随：active 项滚到可视区
  useEffect(() => {
    if (!listRef.current) return;
    const item = listRef.current.querySelector<HTMLElement>(
      `[data-idx="${active}"]`,
    );
    item?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  const choose = useCallback(
    (id: string) => {
      const n = nodes.find((x) => x.id === id);
      if (!n) {
        onClose();
        return;
      }
      // 关闭弹层在 setViewport 之前，否则动画期间两个浮层叠加
      onClose();
      // 选中节点
      select(id);
      // 移动视口到目标：发一个 window 自定义事件，让 CanvasEditor 监听执行 setViewport。
      // 这样能保持单一定位逻辑（CanvasEditor 持有 ReactFlow instance，避免在弹层内 import useReactFlow）。
      window.dispatchEvent(
        new CustomEvent('pea:focus-node', {
          detail: { id: n.id },
        }),
      );
    },
    [nodes, select, onClose],
  );

  // 键盘上下 / Enter
  const onInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, Math.max(matched.length - 1, 0)));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const item = matched[active];
      if (item) choose(item.id);
    }
  };

  // 类别标签定义（图标 + label + key）
  const filters: { key: string; label: string; icon: React.ReactNode }[] = [
    { key: 'all', label: '全部', icon: <AppstoreOutlined /> },
    { key: 'image', label: '图片', icon: <FileImageOutlined /> },
    { key: 'video', label: '视频', icon: <PlayCircleOutlined /> },
    { key: 'text', label: '文本', icon: <span style={{ fontSize: 13 }}>≡</span> },
    { key: 'audio', label: '音频', icon: <SoundOutlined /> },
    { key: 'world3d', label: 'World', icon: <TeamOutlined /> },
    { key: 'group', label: '分组', icon: <AppstoreOutlined /> },
  ];

  const total = nodes.length;
  const hit = matched.length;

  return createPortal(
    <div
      className="pea-search-backdrop"
      onMouseDown={(e) => {
        // mousedown 在 backdrop 上时关闭；面板内点击 stopPropagation 处理
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="搜索节点"
    >
      <div
        className="pea-search-popover"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="pea-search-input-wrap">
          <Input
            ref={inputRef}
            size="large"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKeyDown}
            placeholder="搜索节点…"
            prefix={<SearchOutlined className="pea-search-input-icon" />}
            allowClear
            autoFocus
            variant="borderless"
          />
        </div>

        <div className="pea-search-tabs" role="tablist">
          {filters.map((f) => {
            const isActive = filter === f.key;
            return (
              <button
                key={f.key}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`pea-search-tab${isActive ? ' active' : ''}`}
                onClick={() => setFilter(f.key)}
              >
                <span className="pea-search-tab-icon">{f.icon}</span>
                <span className="pea-search-tab-label">{f.label}</span>
              </button>
            );
          })}
        </div>

        <div className="pea-search-result-meta">
          {query || filter !== 'all'
            ? `匹配 ${hit} / ${total} 个节点`
            : `共 ${total} 个节点`}
        </div>

        <div ref={listRef} className="pea-search-result-list">
          {hit === 0 && (
            <div className="pea-search-empty">
              {total === 0 ? '画布上还没有节点' : '没有匹配的节点'}
            </div>
          )}
          {matched.map((n, i) => {
            const isGroup = (n.type ?? 'pea') === 'group';
            const data = n.data as PeaNodeData;
            return (
              <button
                key={n.id}
                type="button"
                data-idx={i}
                className={`pea-search-item${i === active ? ' active' : ''}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(n.id)}
              >
                <NodeThumb data={data} isGroup={isGroup} />
                <span className="pea-search-item-body">
                  <span className="pea-search-item-title">
                    {data.label || (isGroup ? '分组' : NODE_TITLE_OF(data.kind))}
                  </span>
                  <span className="pea-search-item-sub">
                    {data.prompt
                      ? data.prompt
                      : isGroup
                        ? '分组容器'
                        : '无 Prompt'}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>,
    document.body,
  );
}

/**
 * 节点缩略图组件。
 *
 * 解析顺序：
 *  1) data.resultUrl (字符串)
 *  2) data.resultUrls[data.resultIndex ?? 0] (字符串数组，AI 多结果)
 *  3) data.url (字符串，用户上传本地 blob)
 *  4) data.fileKey (异步签名下载，blob URL)
 *
 * 视频节点：resultUrl/url 视为 poster 帧（多数系统存的是首帧 jpg），fileKey 解析后用 <video preload="metadata"> 让浏览器取首帧。
 * 图片节点：直接 <img>。
 * 分组：显示 AppstoreOutlined。
 * 都没有：按 kind 显示 NodeIcon。
 */
function NodeThumb({ data, isGroup }: { data: PeaNodeData; isGroup: boolean }) {
  const inline = useMemo(() => resolveInlineThumb(data), [data]);
  const [resolvedKeyUrl, setResolvedKeyUrl] = useState<string>('');

  // 异步 fileKey 解析
  useEffect(() => {
    let alive = true;
    if (!inline && data.fileKey) {
      getFileUrl(data.fileKey)
        .then((u) => { if (alive) setResolvedKeyUrl(u); })
        .catch(() => { if (alive) setResolvedKeyUrl(''); });
    } else {
      setResolvedKeyUrl('');
    }
    return () => { alive = false; };
  }, [data.fileKey, inline]);

  const src = inline || resolvedKeyUrl;

  if (isGroup) {
    return (
      <span className="pea-search-item-thumb">
        <span className="pea-search-item-icon-fallback">
          <AppstoreOutlined />
        </span>
      </span>
    );
  }

  if (src) {
    // 视频：先当 poster 显示（多数 resultUrl 实际是首帧 jpg）。
    // 如果 src 明显是视频文件（fileKey 解析出的 blob 通常就是视频），
    // 退化为播放图标 + 半透明遮罩，避免 <video> 阻塞 30+ 行渲染。
    const kind = data.kind;
    if (kind === 'video' && resolvedKeyUrl && !inline) {
      return (
        <span className="pea-search-item-thumb">
          <video
            src={src}
            preload="metadata"
            muted
            playsInline
            // 仅取首帧，不自动播放
            onLoadedData={(e) => {
              const v = e.currentTarget;
              try { v.currentTime = 0.1; } catch { /* ignore */ }
            }}
          />
          <span className="pea-search-item-thumb-overlay">
            <PlayCircleOutlined />
          </span>
        </span>
      );
    }
    return (
      <span className="pea-search-item-thumb">
        <img src={src} alt="" loading="lazy" />
        {kind === 'video' && (
          <span className="pea-search-item-thumb-overlay">
            <PlayCircleOutlined />
          </span>
        )}
      </span>
    );
  }

  return (
    <span className="pea-search-item-thumb">
      <span className="pea-search-item-icon-fallback">
        <NodeIcon kind={data.kind} size={20} />
      </span>
    </span>
  );
}

/** 同步可解析的缩略图地址（不含 fileKey）。 */
function resolveInlineThumb(data: PeaNodeData): string {
  if (data.resultUrl) return data.resultUrl;
  if (data.resultUrls && data.resultUrls.length) {
    const idx = Math.max(0, Math.min(data.resultIndex ?? 0, data.resultUrls.length - 1));
    const u = data.resultUrls[idx];
    if (u) return u;
  }
  if (data.url) return data.url;
  return '';
}

const KIND_LABEL_MAP: Record<string, string> = {
  text: '文本',
  image: 'Image',
  video: '视频',
  audio: '音频',
  ref: '参考',
  generate: '生成',
  agent: '智能体',
  story: '故事',
  world3d: '3D 世界',
  camera: '镜头',
  light: '灯光',
  playlist: '播放列表',
  replace: '替换',
  prompt: 'Prompt',
};

function NODE_TITLE_OF(kind?: string) {
  if (!kind) return '节点';
  return KIND_LABEL_MAP[kind] || '节点';
}
