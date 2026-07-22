import { useEffect, useRef, useState } from 'react';
import { Button, Dropdown, Empty, Tag, Tooltip } from 'antd';
import {
  ClearOutlined,
  RobotOutlined,
  SendOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { api } from '../api/client';
import { useAgent, AgentModel } from '../store/agent';
import { useCanvas } from '../store/canvas';

const SKILLS = [
  { key: 'gen', label: '⚡ 生成图片', prompt: '帮我生成一个图片节点，提示词：一只在星空下奔跑的猫' },
  { key: 'text', label: '✍️ 写文案', prompt: '给我加一个文本节点，内容是产品卖点文案' },
  { key: 'sum', label: '📊 总结画布', prompt: '总结一下当前画布' },
  { key: 'opt', label: '🛠 优化提示词', prompt: '帮我优化这个提示词：好看的图' },
  { key: 'help', label: '❓ 能做什么', prompt: '帮助' },
];

const MODEL_LABEL: Record<AgentModel, string> = {
  fast: '极速',
  standard: '标准',
  pro: '专业',
};

/**
 * Agent 对话面板 (T-M1-08, FR-M1-50~53)：
 * 输入 / 技能芯片 / 模型切换 / 打字动画 / 规则引擎兜底。
 * 规则引擎可真正创建节点、触发生成，让面板"活"起来。
 */
export default function AgentPanel() {
  const { open, model, messages, typing, toggle, setModel, push, setTyping, reset } = useAgent();
  const addNode = useCanvas((s) => s.addNode);
  const [input, setInput] = useState('');
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, typing]);

  if (!open) {
    return (
      <button
        onClick={toggle}
        className="absolute bottom-4 right-4 z-30 flex h-11 w-11 items-center justify-center rounded-full bg-pea-brand text-white shadow-lg transition hover:scale-105"
        aria-label="打开副驾驶"
      >
        <RobotOutlined />
      </button>
    );
  }

  // 规则引擎：根据指令返回动作/回复
  const runRule = (text: string) => {
    const t = text.trim();
    const lower = t.toLowerCase();
    if (lower.includes('生成') || lower.includes('图片') || lower.includes('gen')) {
      addNode({ kind: 'generate', label: '生成', prompt: t.replace(/.*[:：]\s*/, '') || '一只在星空下奔跑的猫' }, {
        x: 320 + Math.random() * 80,
        y: 160 + Math.random() * 80,
      });
      return '已为你添加一个「生成」节点 ⚡，在右侧属性面板填好提示词后点生成即可。';
    }
    if (lower.includes('文案') || lower.includes('文本') || lower.includes('text')) {
      addNode(
        { kind: 'text', label: '文案', html: '<b>产品卖点</b><br/>· 轻奢质感<br/>· 高性价比<br/>· 顺丰包邮' },
        { x: 160 + Math.random() * 80, y: 200 + Math.random() * 80 },
      );
      return '已添加「文本」节点，双击可在画布上编辑富文本。';
    }
    if (lower.includes('总结')) {
      const nodes = useCanvas.getState().nodes;
      const byKind: Record<string, number> = {};
      nodes.forEach((n) => (byKind[n.data.kind] = (byKind[n.data.kind] ?? 0) + 1));
      const summary = Object.entries(byKind)
        .map(([k, v]) => `${k}:${v}`)
        .join('，') || '空';
      return `当前画布共 ${nodes.length} 个节点（${summary}）。`;
    }
    if (lower.includes('优化') || lower.includes('提示词') || lower.includes('opt')) {
      return '优化建议：① 加主体与场景（如「一只在霓虹城市奔跑的橘猫」）；② 加风格（胶片/3D/水彩）；③ 加画质词（8k、超清、光线追踪）。';
    }
    if (lower.includes('帮助') || lower === '?') {
      return '我可以：⚡生成图片节点、✍️写文案、📊总结画布、🛠优化提示词。直接说需求即可（当前为规则引擎兜底，接入大模型后能力更强）。';
    }
    return `收到：「${t}」。我是规则引擎兜底版，已记录你的意图。可尝试「生成图片」「写文案」「总结画布」等指令。`;
  };

  const send = (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || typing) return;
    push('user', content);
    setInput('');
    setTyping(true);
    // 模拟思考延迟 + 打字动画
    window.setTimeout(() => {
      const reply = runRule(content);
      setTyping(false);
      push('assistant', reply);
      // 若是生成类指令，顺手触发一次生成受理演示
      if (content.includes('生成') && content.includes('图片')) {
        const gen = useCanvas.getState().nodes.find((n) => n.data.kind === 'generate');
        if (gen?.data.prompt) {
          api
            .post('/generation/jobs', { type: 'image', prompt: gen.data.prompt, priority: 'normal' })
            .then(() => push('assistant', '已自动受理该生成任务，进度会在右侧属性面板更新。'))
            .catch(() => {});
        }
      }
    }, 650);
  };

  return (
    <div className="absolute bottom-0 right-0 z-30 flex h-[60%] w-[360px] flex-col rounded-tl-2xl border border-black/10 bg-white/95 shadow-2xl backdrop-blur dark:border-white/10 dark:bg-[#14141a]/95">
      {/* header */}
      <div className="flex items-center justify-between border-b border-black/5 px-3 py-2 dark:border-white/10">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <RobotOutlined className="text-pea-brand" /> 副驾驶
        </div>
        <div className="flex items-center gap-1">
          <Dropdown
            menu={{
              items: (['fast', 'standard', 'pro'] as AgentModel[]).map((m) => ({
                key: m,
                label: MODEL_LABEL[m],
              })),
              onClick: ({ key }) => setModel(key as AgentModel),
            }}
          >
            <Tag color="blue" className="cursor-pointer" aria-label="模型切换">
              {MODEL_LABEL[model]}
            </Tag>
          </Dropdown>
          <Tooltip title="清空对话">
            <Button type="text" size="small" icon={<ClearOutlined />} onClick={reset} />
          </Tooltip>
          <Tooltip title="收起">
            <Button type="text" size="small" onClick={toggle} aria-label="收起副驾驶">
              ✕
            </Button>
          </Tooltip>
        </div>
      </div>

      {/* messages */}
      <div ref={listRef} className="flex-1 space-y-2 overflow-y-auto p-3 text-sm">
        {messages.length === 0 && <Empty description="开始对话" />}
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'text-right' : 'text-left'}>
            <div
              className={
                'inline-block max-w-[85%] rounded-2xl px-3 py-2 ' +
                (m.role === 'user'
                  ? 'bg-pea-brand text-white'
                  : 'bg-black/5 text-gray-800 dark:bg-white/10 dark:text-gray-100')
              }
            >
              {m.content}
            </div>
          </div>
        ))}
        {typing && (
          <div className="text-left">
            <div className="inline-flex gap-1 rounded-2xl bg-black/5 px-3 py-2 dark:bg-white/10">
              <span className="animate-bounce">●</span>
              <span className="animate-bounce" style={{ animationDelay: '0.15s' }}>●</span>
              <span className="animate-bounce" style={{ animationDelay: '0.3s' }}>●</span>
            </div>
          </div>
        )}
      </div>

      {/* skill chips */}
      <div className="flex flex-wrap gap-1 px-3 pb-2">
        {SKILLS.map((s) => (
          <button
            key={s.key}
            onClick={() => send(s.prompt)}
            className="rounded-full border border-pea-brand/40 px-2 py-0.5 text-xs text-pea-brand transition hover:bg-pea-brand hover:text-white"
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* input */}
      <div className="flex items-center gap-2 border-t border-black/5 p-2 dark:border-white/10">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="输入指令，回车发送…"
          className="flex-1 rounded-lg border border-black/10 bg-transparent px-3 py-1.5 text-sm outline-none focus:border-pea-brand dark:border-white/10"
        />
        <Button type="primary" shape="circle" icon={<SendOutlined />} onClick={() => send()} aria-label="发送" />
      </div>
    </div>
  );
}
