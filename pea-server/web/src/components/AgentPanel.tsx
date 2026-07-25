import { useEffect, useRef, useState } from 'react';
import { Button, Dropdown, Empty, Tag, Tooltip } from 'antd';
import {
  BellOutlined,
  ClearOutlined,
  CloseOutlined,
  ExpandOutlined,
  MessageOutlined,
  SendOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { api } from '../api/client';
import { listAvailableModels } from '../api/catalog';
import type { AvailableModel } from '../api/catalog';
import { useAgent, AgentModel } from '../store/agent';
import { useAuth } from '../store/auth';
import { useCanvas } from '../store/canvas';

const SKILLS = [
  { key: 'gen', label: '⚡ 生成图片', prompt: '帮我生成一个图片节点，提示词：一只在星空下奔跑的猫' },
  { key: 'text', label: '✍️ 写文案', prompt: '给我加一个文本节点，内容是产品卖点文案' },
  { key: 'sum', label: '📊 总结画布', prompt: '总结一下当前画布' },
  { key: 'opt', label: '🛠 优化提示词', prompt: '帮我优化这个提示词：好看的图' },
  { key: 'help', label: '❓ 能做什么', prompt: '帮助' },
];

const SUGGESTIONS = [
  {
    key: 'skill',
    icon: '⚡',
    title: '把这个项目的风格做成 Skill',
    desc: '请把这个项目的风格沉淀成可复用的 Skill 方案。请先给我若干个可选方...',
    tag: null,
  },
  {
    key: 'brainstorm',
    icon: '🧠',
    title: '体验 Brainstorm 模式设计人物关系',
    desc: '头脑风暴 请用 Brainstorm 模式帮我设计人物关系。请提出几组...',
    tag: '头脑风暴',
  },
];

const MODEL_LABEL: Record<AgentModel, string> = {
  fast: '极速',
  standard: '标准',
  pro: '专业',
};

/** 副驾驶 AI 聊天侧边栏（对齐参考图）：
 *  - 收起：右下角圆形 pea logo 按钮
 *  - 展开：右侧固定侧边栏，含新建对话头部、问候语、技能建议卡片、聊天消息、底部输入区
 */
export default function AgentPanel() {
  const { open, model, messages, typing, toggle, setModel, push, setTyping, reset } = useAgent();
  const addNode = useCanvas((s) => s.addNode);
  const user = useAuth((s) => s.user);
  const [input, setInput] = useState('');
  const listRef = useRef<HTMLDivElement>(null);
  // 默认图片生成模型（供"生成图片"指令真实提交，标签动态展示）
  const [genModel, setGenModel] = useState<AvailableModel | null>(null);

  useEffect(() => {
    listAvailableModels('image')
      .then((list) => setGenModel(list.find((m) => m.isDefault) ?? list[0] ?? null))
      .catch(() => setGenModel(null));
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, typing]);

  if (!open) {
    return (
      <button
        onClick={toggle}
        className="pea-agent-bubble"
        aria-label="打开副驾驶"
        title="打开副驾驶"
      >
        <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" className="pea-agent-bubble-icon">
          <path d="M7 10c4-3 14-3 18 0" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
          <path d="M5 16c6-4 16-4 22 0" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
          <path d="M7 22c4-3 14-3 18 0" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
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
    window.setTimeout(() => {
      const reply = runRule(content);
      setTyping(false);
      push('assistant', reply);
      if (content.includes('生成') && content.includes('图片')) {
        const gen = useCanvas.getState().nodes.find((n) => n.data.kind === 'generate');
        if (gen?.data.prompt) {
          api
            .post('/generation/jobs', {
              type: 'image',
              prompt: gen.data.prompt,
              model: genModel?.id,
              priority: 'normal',
            })
            .then(() =>
              push('assistant', `已自动受理该生成任务（${genModel?.displayName ?? '默认模型'}），进度会在右侧属性面板更新。`),
            )
            .catch(() => {});
        }
      }
    }, 650);
  };

  const displayName = user?.displayName || user?.email?.split('@')[0] || '创作者';
  const hasMessages = messages.length > 0;

  return (
    <aside className="pea-agent-panel" aria-label="副驾驶聊天">
      {/* header */}
      <div className="pea-agent-header">
        <Dropdown
          menu={{
            items: [
              { key: 'new', label: '新建对话', icon: <MessageOutlined /> },
              { key: 'history', label: '历史对话' },
            ],
            onClick: ({ key }) => {
              if (key === 'new') reset();
            },
          }}
        >
          <button className="pea-agent-title" aria-label="新建对话">
            <MessageOutlined />
            <span>新建对话</span>
            <span className="pea-agent-title-arrow">⌄</span>
          </button>
        </Dropdown>
        <div className="pea-agent-actions">
          <Tooltip title="通知">
            <Button type="text" size="small" icon={<BellOutlined />} aria-label="通知" />
          </Tooltip>
          <Tooltip title="展开">
            <Button type="text" size="small" icon={<ExpandOutlined />} aria-label="展开" />
          </Tooltip>
          <Tooltip title="清空">
            <Button type="text" size="small" icon={<ClearOutlined />} onClick={reset} aria-label="清空对话" />
          </Tooltip>
          <Tooltip title="收起">
            <Button type="text" size="small" icon={<CloseOutlined />} onClick={toggle} aria-label="收起副驾驶" />
          </Tooltip>
        </div>
      </div>

      {/* main scroll area */}
      <div ref={listRef} className="pea-agent-body">
        {!hasMessages ? (
          <div className="pea-agent-welcome">
            <div className="pea-agent-welcome-logo">
              <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M7 10c4-3 14-3 18 0" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                <path d="M5 16c6-4 16-4 22 0" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                <path d="M7 22c4-3 14-3 18 0" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
              </svg>
            </div>
            <div className="pea-agent-welcome-title">Hi {displayName}!</div>
            <div className="pea-agent-welcome-subtitle">今天一起创作点什么？</div>
            <div className="pea-agent-suggestions">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.key}
                  className="pea-agent-suggestion"
                  onClick={() => send(s.desc)}
                >
                  <div className="pea-agent-suggestion-top">
                    <span className="pea-agent-suggestion-icon">{s.icon}</span>
                    <span className="pea-agent-suggestion-title">{s.title}</span>
                  </div>
                  <div className="pea-agent-suggestion-desc">{s.desc}</div>
                  {s.tag && <span className="pea-agent-suggestion-tag">{s.tag}</span>}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="pea-agent-messages">
            {messages.map((m) => (
              <div key={m.id} className={m.role === 'user' ? 'pea-agent-msg user' : 'pea-agent-msg assistant'}>
                <div className="pea-agent-msg-bubble">{m.content}</div>
              </div>
            ))}
            {typing && (
              <div className="pea-agent-msg assistant">
                <div className="pea-agent-msg-bubble pea-agent-typing">
                  <span className="animate-bounce">●</span>
                  <span className="animate-bounce" style={{ animationDelay: '0.15s' }}>●</span>
                  <span className="animate-bounce" style={{ animationDelay: '0.3s' }}>●</span>
                </div>
              </div>
            )}
            {!typing && messages.length === 0 && <Empty description="开始对话" />}
          </div>
        )}
      </div>

      {/* skill chips (shown when there are messages) */}
      {hasMessages && (
        <div className="pea-agent-chips">
          {SKILLS.map((s) => (
            <button
              key={s.key}
              onClick={() => send(s.prompt)}
              className="pea-agent-chip"
            >
              {s.label}
            </button>
          ))}
        </div>
      )}

      {/* input */}
      <div className="pea-agent-input-wrap">
        <div className="pea-agent-input-top">
          <button className="pea-agent-input-plus" aria-label="添加附件" title="添加附件">+</button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder="描述创意或需求，/ 使用技能，@ 添加画布内容，@ 引用参考或使用插件"
            className="pea-agent-input"
          />
        </div>
        <div className="pea-agent-input-bar">
          <button className="pea-agent-input-confirm" onClick={() => send('手动确认')}>
            <ThunderboltOutlined /> 手动确认
          </button>
          <div className="pea-agent-input-right">
            <Dropdown
              menu={{
                items: (['fast', 'standard', 'pro'] as AgentModel[]).map((m) => ({
                  key: m,
                  label: MODEL_LABEL[m],
                })),
                onClick: ({ key }) => setModel(key as AgentModel),
              }}
            >
              <Tag color="blue" className="cursor-pointer" aria-label="当前生成模型">
                {genModel ? genModel.displayName : 'AI 助手'}
              </Tag>
            </Dropdown>
            <button className="pea-agent-input-mic" aria-label="语音输入" title="语音输入">🎤</button>
            <button
              className="pea-agent-input-send"
              aria-label="发送"
              disabled={!input.trim() || typing}
              onClick={() => send()}
            >
              <SendOutlined />
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
