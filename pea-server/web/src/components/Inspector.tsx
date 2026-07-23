import { useEffect, useRef, useState } from 'react';
import { App, Button, Input, Progress, Tag, Typography } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { api } from '../api/client';
import { useCanvas } from '../store/canvas';
import { NODE_DEF_OF } from '../constants/nodeTypes';
import RichTextToolbar from './RichTextToolbar';

export default function Inspector() {
  const { nodes, selectedId, updateNodeData } = useCanvas();
  const node = nodes.find((n) => n.id === selectedId);
  const [job, setJob] = useState<{ id: string; status: string; progress: number } | null>(null);
  const { message } = App.useApp();
  const editorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onEvent = (e: Event) => {
      const ev = (e as CustomEvent).detail;
      if (ev.kind === 'job.updated' && job && ev.jobId === job.id) {
        setJob({ id: ev.jobId, status: ev.status, progress: Math.round((ev.progress ?? 1) * 100) });
        if (ev.status === 'done') message.success('生成完成');
        if (ev.status === 'failed') message.error('生成失败，已退款');
      }
    };
    window.addEventListener('pea:event', onEvent);
    return () => window.removeEventListener('pea:event', onEvent);
  }, [job]);

  if (!node) {
    return (
      <div className="p-4 text-sm text-gray-400">选中一个节点以查看 / 编辑属性</div>
    );
  }

  const onGenerate = async () => {
    if (!node.data.prompt) return message.warning('请先填写生成提示词');
    try {
      const { data } = await api.post('/generation/jobs', {
        type: 'image',
        prompt: node.data.prompt,
        priority: 'normal',
      });
      setJob({ id: data.jobId, status: 'queued', progress: 0 });
      message.info('已受理，任务运行中…');
    } catch (e: any) {
      message.error(e?.response?.data?.message ?? '受理失败');
    }
  };

  return (
    <div className="flex h-full w-72 flex-col border-l border-black/5 p-4 dark:border-white/10">
      <Typography.Title level={5}>属性</Typography.Title>
      <label className="mb-1 text-xs text-gray-500">类型</label>
      <div className="mb-3 flex items-center gap-2 text-sm">
        <span>{NODE_DEF_OF(node.data.kind).icon}</span>
        <span className="font-medium">{NODE_DEF_OF(node.data.kind).label}</span>
      </div>
      <label className="mb-1 text-xs text-gray-500">标签</label>
      <Input
        value={node.data.label}
        onChange={(e) => updateNodeData(node.id, { label: e.target.value })}
        className="mb-3"
      />
      {node.data.kind === 'text' && (
        <>
          <label className="mb-1 text-xs text-gray-500">富文本</label>
          <RichTextToolbar editorRef={editorRef} />
          <div
            key={node.id}
            ref={editorRef}
            contentEditable
            suppressContentEditableWarning
            onInput={(e) => updateNodeData(node.id, { html: e.currentTarget.innerHTML })}
            className="min-h-[120px] flex-1 overflow-auto rounded-lg border border-black/10 bg-black/5 p-2 text-sm dark:border-white/10 dark:bg-white/5"
            dangerouslySetInnerHTML={{ __html: node.data.html ?? '<p>在此输入文本…</p>' }}
          />
        </>
      )}
      {node.data.kind === 'generate' && (
        <>
          <label className="mb-1 text-xs text-gray-500">提示词</label>
          <Input.TextArea
            rows={4}
            value={node.data.prompt ?? ''}
            onChange={(e) => updateNodeData(node.id, { prompt: e.target.value })}
            className="mb-3"
          />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            block
            loading={job?.status === 'queued' || job?.status === 'running'}
            onClick={onGenerate}
          >
            ⚡ 生成
          </Button>
          {job && (
            <div className="mt-3">
              <Tag color={job.status === 'done' ? 'green' : 'blue'}>{job.status}</Tag>
              <Progress percent={job.progress} />
            </div>
          )}
        </>
      )}
      {node.data.kind !== 'text' && node.data.kind !== 'generate' && (
        <div className="mt-2 rounded-lg border border-black/5 p-2 text-xs text-gray-400 dark:border-white/10">
          该节点类型的参数编辑将随后续迭代接入。
        </div>
      )}
    </div>
  );
}
