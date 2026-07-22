import { useRef, useState } from 'react';
import { App, Button, Input, Tabs, Tag, Tooltip } from 'antd';
import {
  CloseOutlined,
  FileTextOutlined,
  HistoryOutlined,
  MessageOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { api } from '../api/client';
import { useCanvas } from '../store/canvas';

/**
 * 侧边面板 (T-M1-Next-01, FR-M1-60~63)：搜索 / 评论 / 历史 / 文件。
 * 左停靠、可收起。文件走预签名直传真实链路。
 */
export default function SidePanel({ onClose }: { onClose: () => void }) {
  const { nodes, select, saveCount } = useCanvas();
  const { message } = App.useApp();
  const [query, setQuery] = useState('');
  const [comments, setComments] = useState<{ who: string; text: string; ts: number }[]>([]);
  const [commentInput, setCommentInput] = useState('');
  const [files, setFiles] = useState<{ key: string; status: string }[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);

  const filtered = query
    ? nodes.filter((n) => n.data.label.toLowerCase().includes(query.toLowerCase()))
    : nodes;

  const addComment = () => {
    const t = commentInput.trim();
    if (!t) return;
    setComments((c) => [...c, { who: '我', text: t, ts: Date.now() }]);
    setCommentInput('');
  };

  const upload = async (file: File) => {
    const key = `uploads/${Date.now()}-${file.name}`;
    try {
      const { data } = await api.post('/files/presign', { key, expiresSec: 600 });
      await fetch(data.uploadUrl, { method: 'PUT', body: file });
      setFiles((f) => [...f, { key, status: '已上传' }]);
      message.success('文件已上传');
    } catch (e: any) {
      setFiles((f) => [...f, { key, status: '失败' }]);
      message.warning('上传未完成（存储地址浏览器可能不可达）');
    }
  };

  const tabItems = [
    {
      key: 'search',
      label: (
        <span>
          <SearchOutlined /> 搜索
        </span>
      ),
      children: (
        <div className="space-y-2">
          <Input
            placeholder="按标签搜索节点"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            prefix={<SearchOutlined />}
          />
          <div className="space-y-1">
            {filtered.map((n) => (
              <button
                key={n.id}
                onClick={() => select(n.id)}
                className="block w-full rounded-md border border-black/5 px-2 py-1.5 text-left text-sm hover:bg-pea-brand/10 dark:border-white/10"
              >
                {n.data.label} <Tag className="ml-1">{n.data.kind}</Tag>
              </button>
            ))}
            {filtered.length === 0 && <div className="text-xs text-gray-400">无匹配节点</div>}
          </div>
        </div>
      ),
    },
    {
      key: 'comments',
      label: (
        <span>
          <MessageOutlined /> 评论
        </span>
      ),
      children: (
        <div className="space-y-2">
          <div className="space-y-1">
            {comments.map((c, i) => (
              <div key={i} className="rounded-md bg-black/5 p-2 text-xs dark:bg-white/5">
                <b>{c.who}</b>：{c.text}
              </div>
            ))}
            {comments.length === 0 && <div className="text-xs text-gray-400">还没有评论</div>}
          </div>
          <Input.TextArea
            rows={2}
            placeholder="写下评论…"
            value={commentInput}
            onChange={(e) => setCommentInput(e.target.value)}
          />
          <Button block onClick={addComment}>
            发表
          </Button>
        </div>
      ),
    },
    {
      key: 'history',
      label: (
        <span>
          <HistoryOutlined /> 历史
        </span>
      ),
      children: (
        <div className="space-y-1 text-sm">
          <div className="rounded-md bg-black/5 p-2 dark:bg-white/5">自动保存次数：{saveCount}</div>
          <div className="rounded-md bg-black/5 p-2 dark:bg-white/5">版本号：{useCanvas.getState().version}</div>
          <div className="text-xs text-gray-400">编辑后每 1s 自动保存（PRD 痛点：刷新不丢）</div>
        </div>
      ),
    },
    {
      key: 'files',
      label: (
        <span>
          <FileTextOutlined /> 文件
        </span>
      ),
      children: (
        <div className="space-y-2">
          <input
            ref={fileInput}
            type="file"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
            }}
          />
          <Button icon={<UploadOutlined />} block onClick={() => fileInput.current?.click()}>
            上传文件
          </Button>
          <div className="space-y-1">
            {files.map((f, i) => (
              <div key={i} className="truncate rounded-md bg-black/5 p-2 text-xs dark:bg-white/5">
                {f.key} <Tag color={f.status === '已上传' ? 'green' : 'red'}>{f.status}</Tag>
              </div>
            ))}
            {files.length === 0 && <div className="text-xs text-gray-400">暂无文件</div>}
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="absolute left-0 top-0 z-20 flex h-full w-72 flex-col border-r border-black/10 bg-white/95 shadow-xl backdrop-blur dark:border-white/10 dark:bg-[#14141a]/95">
      <div className="flex items-center justify-between border-b border-black/5 px-3 py-2 dark:border-white/10">
        <span className="text-sm font-semibold">面板</span>
        <Tooltip title="收起">
          <Button type="text" size="small" icon={<CloseOutlined />} onClick={onClose} aria-label="收起面板" />
        </Tooltip>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <Tabs items={tabItems} size="small" />
      </div>
    </div>
  );
}
