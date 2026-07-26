p = r"C:\workspace\pea\pea-server\web\src\components\NodeChatPrompt.tsx"
with open(p, "r", encoding="utf-8") as f:
    s = f.read()

marker = "\n    </div>\n  );\n}"
idx = s.rfind(marker)
assert idx != -1, "marker not found"

popup = """      {/* ═════════ 平台配置浮层（Phase2 提示词构造层）═════════════ */}
      {pcPickerOpen && (genType === 'image' || genType === 'video') && pcTriggerRect && createPortal(
        <div
          ref={pcRef}
          className="node-pc-picker"
          style={{
            position: 'fixed',
            left: pcTriggerRect.left,
            top: (pcTriggerRect.bottom ?? pcTriggerRect.top + 30) + 8,
            width: 280,
          }}
          role="dialog"
          aria-label="选择平台配置"
        >
          <div className="picker-scroll">
            <button
              type="button"
              className={`picker-card${platformConfigId === '' ? ' picker-card-active' : ''}`}
              onClick={() => { setPlatformConfigId(''); setPcPickerOpen(false); }}
            >
              <div className="picker-card-head">
                <span className="picker-card-name">不指定（直接用聊天原文）</span>
              </div>
            </button>
            {platformConfigs.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`picker-card${platformConfigId === c.id ? ' picker-card-active' : ''}`}
                onClick={() => { setPlatformConfigId(c.id); setPcPickerOpen(false); }}
              >
                <div className="picker-card-head">
                  <span className="picker-card-name">{c.name}</span>
                  {c.isDefault && <span className="picker-badge picker-badge-new">DEFAULT</span>}
                </div>
                <div className="picker-card-tags">
                  <span className="picker-tag">{c.platform}</span>
                  <span className="picker-tag">{c.promptMode === 'llm' ? 'LLM 扩写' : '模板拼装'}</span>
                </div>
              </button>
            ))}
            {platformConfigs.length === 0 && (
              <div className="picker-empty">暂无平台配置，可在「AI Provider 设置」中创建</div>
            )}
          </div>
        </div>,
        document.body
      )}

"""
new = s[:idx] + popup + s[idx:]
with open(p, "w", encoding="utf-8") as f:
    f.write(new)
print("inserted; new length", len(new))
