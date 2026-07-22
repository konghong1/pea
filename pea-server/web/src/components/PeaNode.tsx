import { Handle, Position, NodeProps } from 'reactflow';
import { useCanvas, PeaNodeData } from '../store/canvas';

export default function PeaNode({ id, data, selected }: NodeProps<PeaNodeData>) {
  const update = useCanvas((s) => s.updateNodeData);
  const kindColor: Record<string, string> = {
    prompt: '#6C5CE7',
    text: '#00CEC9',
    image: '#FD79A8',
    generate: '#0984E3',
  };
  return (
    <div className={`pea-node ${selected ? 'ring-2 ring-pea-brand' : ''}`}>
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center gap-2 px-3 py-2">
        <span
          className="h-2.5 w-2.5 rounded-full"
          style={{ background: kindColor[data.kind] }}
        />
        <span className="text-sm font-medium">{data.label}</span>
      </div>
      {data.kind === 'text' && data.html && (
        <div
          className="max-h-24 overflow-hidden px-3 pb-2 text-xs opacity-80"
          dangerouslySetInnerHTML={{ __html: data.html }}
        />
      )}
      {data.kind === 'generate' && (
        <div className="px-3 pb-2">
          <textarea
            className="w-full rounded-md border border-black/10 bg-black/5 p-1 text-xs dark:border-white/10 dark:bg-white/5"
            placeholder="生成提示词…"
            value={data.prompt ?? ''}
            onChange={(e) => update(id, { prompt: e.target.value })}
            rows={2}
          />
        </div>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
