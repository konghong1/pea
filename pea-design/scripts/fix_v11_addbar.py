import re

path = 'pea-canvas-v11.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Exact HTML block as it appears in v11
old_html = '''    <div class="add-pal-top">
      <div class="add-pal-tools">
        <button class="add-pal-ibtn" title="图片" onclick="toast('选择图片…')">✨</button>
        <button class="add-pal-ibtn" title="菜单" onclick="toast('打开菜单…')">☰</button>
        <button class="add-pal-ibtn" title="添加节点" onclick="document.getElementById('addPopInput').focus()">✚</button>
      </div>
      <textarea id="addPopInput" class="add-pal-input" rows="1" placeholder="描述任何你想要生成的内容"
        oninput="this.style.height='auto';this.style.height=this.scrollHeight+'px'"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();addNodeFromBar();}"></textarea>
    </div>
    <div class="add-pal-bar">
      <div class="add-pal-lefttools">
        <span class="add-pal-model" onclick="toast('切换模型…')"><span class="star">✦</span> Seedream 5.0 Lite</span>
        <span class="add-pal-chip" onclick="toast('切换比例…')">☐ 1:1</span>
        <span class="add-pal-chip" onclick="toast('切换画质…')">2K</span>
      </div>
      <div class="add-pal-righttools">
        <button class="add-pal-act" title="语音输入">🎤</button>
        <button class="add-pal-act" title="生成数量">1×</button>
        <button class="add-pal-act" title="设置" style="font-size:13px;">⚙<span class="add-pal-badge">5</span></button>
        <button class="add-pal-send" title="发送" onclick="addNodeFromBar()">↑</button>
      </div>
    </div>'''

new_html = '''    <div class="add-pal-top">
      <div class="add-pal-tools">
        <button class="add-pal-ibtn" title="图片" onclick="toast('选择图片…')">🖼</button>
        <button class="add-pal-ibtn" title="添加节点" onclick="document.getElementById('addPopInput').focus()">✚</button>
      </div>
      <textarea id="addPopInput" class="add-pal-input" rows="1" placeholder="描述任何你想要生成的内容"
        oninput="this.style.height='auto';this.style.height=this.scrollHeight+'px'"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();addNodeFromBar();}"></textarea>
    </div>
    <div class="add-pal-bar">
      <div class="add-pal-lefttools">
        <span class="add-pal-model" onclick="toast('切换模型…')"><span class="star">◈</span> Gemini 3.1 Flash Lite</span>
      </div>
      <div class="add-pal-righttools">
        <button class="add-pal-act" title="语音输入">🎤</button>
        <button class="add-pal-act" title="生成数量">1×</button>
        <button class="add-pal-act" title="设置" style="font-size:13px;">⚙<span class="add-pal-badge">1</span></button>
        <button class="add-pal-send" title="发送" onclick="addNodeFromBar()">↑</button>
      </div>
    </div>'''

if old_html in content:
    content = content.replace(old_html, new_html)
    print('HTML replaced OK')
else:
    print('HTML block NOT FOUND')

# Remove chip CSS
old_css = '''.add-pal-chip{
  font-size:11px;color:#9ca3af;cursor:pointer;padding:5px 9px;border-radius:8px;
  border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.04);transition:.12s;white-space:nowrap;
}
.add-pal-chip:hover{ background:rgba(255,255,255,.08); color:#d1d5db; }
'''
if old_css in content:
    content = content.replace(old_css, '')
    print('chip CSS removed')

# Tweak model icon color to cyan accent
content = content.replace('.add-pal-model .star{ font-size:11px; color:#e5e7eb; }',
                          '.add-pal-model .star{ font-size:11px; color:var(--accent); }')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
