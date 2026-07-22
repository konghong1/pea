import re

path = r'D:\workspace\ai-agent\pea-canvas-v12.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# 1) Replace openAddPopover + addNodeFromBar block to be mode-aware
old_block = '''let _addAt = null;
function openAddPopover(e, vx, vy){
  e.stopPropagation(); closePopups();
  if(vx != null){
    _addAt = { x: vx - 90, y: vy - 40 };
  } else {
    _addAt = null;
  }
  const p = document.createElement('div'); p.className='popover add-pal'; p.id='addPop';
  p.innerHTML = `
    <div class="add-pal-top">
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
    </div>`;
  document.body.appendChild(p);
  const inp = p.querySelector('#addPopInput'); if(inp) inp.focus();
}
function addNodeFromBar(){
  const inp = document.getElementById('addPopInput'); if(!inp || !inp.value.trim()){ toast('请输入内容'); return; }
  const type = Object.keys(NODE_DEFS)[Math.floor(Math.random() * Object.keys(NODE_DEFS).length)];
  addNode(type, _addAt ? _addAt.x : undefined, _addAt ? _addAt.y : undefined);
  toast('已添加节点'); closePopups();
}'''

new_block = '''let _addAt = null;
let _addBarMode = 'image';
function addBarHTML(mode){
  const isText = mode === 'text';
  const leftBtns = isText
    ? `<button class="add-pal-ibtn" title="图片" onclick="toast('选择图片…')">🖼</button>
        <button class="add-pal-ibtn" title="添加节点" onclick="document.getElementById('addPopInput').focus()">✚</button>`
    : `<button class="add-pal-ibtn" title="灵感" onclick="toast('灵感提示…')">✨</button>
        <button class="add-pal-ibtn" title="菜单" onclick="toast('打开菜单…')">☰</button>
        <button class="add-pal-ibtn" title="添加节点" onclick="document.getElementById('addPopInput').focus()">✚</button>`;
  const model = isText
    ? `<span class="add-pal-model" onclick="toast('切换模型…')"><span class="star">◈</span> Gemini 3.1 Flash Lite</span>`
    : `<span class="add-pal-model" onclick="toast('切换模型…')"><span class="star">📊</span> Seedream 5.0 Lite</span>
        <span class="add-pal-chip" onclick="toast('设置比例…')">1:1</span>
        <span class="add-pal-chip" onclick="toast('设置分辨率…')">2K</span>`;
  const badge = isText ? '1' : '5';
  return `
    <div class="add-pal-top">
      <div class="add-pal-tools">${leftBtns}</div>
      <textarea id="addPopInput" class="add-pal-input" rows="1" placeholder="描述任何你想要生成的内容"
        oninput="this.style.height='auto';this.style.height=this.scrollHeight+'px'"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();addNodeFromBar();}"></textarea>
    </div>
    <div class="add-pal-bar">
      <div class="add-pal-lefttools">${model}</div>
      <div class="add-pal-righttools">
        <button class="add-pal-act" title="语音输入">🎤</button>
        <button class="add-pal-act" title="生成数量">1×</button>
        <button class="add-pal-act" title="设置" style="font-size:13px;">⚙<span class="add-pal-badge">${badge}</span></button>
        <button class="add-pal-send" title="发送" onclick="addNodeFromBar()">↑</button>
      </div>
    </div>`;
}
function renderAddBar(mode){
  _addBarMode = mode || 'image';
  let p = document.getElementById('addPop');
  if(!p){
    p = document.createElement('div'); p.className='popover add-pal'; p.id='addPop';
    document.body.appendChild(p);
  }
  p.innerHTML = addBarHTML(_addBarMode);
}
function openAddPopover(e, vx, vy){
  if(e && e.stopPropagation) e.stopPropagation(); closePopups();
  if(vx != null){ _addAt = { x: vx - 90, y: vy - 40 }; } else { _addAt = null; }
  renderAddBar('image');
  const inp = document.getElementById('addPopInput'); if(inp) inp.focus();
}
function updateAddBar(){
  const selIds = [...state.sel];
  let mode = 'image';
  if(selIds.length === 1){
    const node = state.nodes.find(n=>n.id===selIds[0]);
    if(node) mode = node.type === 'text' ? 'text' : 'image';
  }
  if(mode !== _addBarMode || !document.getElementById('addPop')){
    renderAddBar(mode);
  }
}
function addNodeFromBar(){
  const inp = document.getElementById('addPopInput'); if(!inp || !inp.value.trim()){ toast('请输入内容'); return; }
  const type = Object.keys(NODE_DEFS)[Math.floor(Math.random() * Object.keys(NODE_DEFS).length)];
  addNode(type, _addAt ? _addAt.x : undefined, _addAt ? _addAt.y : undefined);
  toast('已添加节点'); closePopups();
}'''

if old_block not in html:
    print('ERROR: old block not found')
else:
    html = html.replace(old_block, new_block)
    print('Replaced add-bar block')

# 2) Hook updateAddBar into renderNodes right after updateTextToolbar
old_rn_hook = '  updateTextToolbar();\n}\n\n/* ═══════════════════════════════════════════\n   DRAW CONNECTIONS'
new_rn_hook = '  updateTextToolbar();\n  updateAddBar();\n}\n\n/* ═══════════════════════════════════════════\n   DRAW CONNECTIONS'
if old_rn_hook not in html:
    print('ERROR: renderNodes hook not found')
else:
    html = html.replace(old_rn_hook, new_rn_hook)
    print('Hooked updateAddBar into renderNodes')

# 3) Also update add bar when selection changes via selectOnly/toggleSel/clearSel
# These already call renderNodes (which now calls updateAddBar), so no change needed.

# 4) Make Text node tag say "Text" not "Prompt/文本", and Image node tag say "Image"
# Update NODE_DEFS tags
old_defs = '''const NODE_DEFS = {
  text:    { icon:'T',  grad:'linear-gradient(135deg,#1fa2dc,#2563eb)', title:'文本提示词', body:'输入创意描述或脚本…', tags:['Prompt','文本'], color:'#1fa2dc' },
  image:   { grad:'linear-gradient(135deg,#34d399,#059669)', icon:'🎨', title:'图像生成', body:'Midjourney · Flux · GPT Image\\n尺寸 1024×1024 · 风格: 电影级', tags:['MJ V8.1','生成'], color:'#34d399' },'''
new_defs = '''const NODE_DEFS = {
  text:    { icon:'T',  grad:'linear-gradient(135deg,#1fa2dc,#2563eb)', title:'文本提示词', body:'输入创意描述或脚本…', tags:['Text'], color:'#1fa2dc' },
  image:   { grad:'linear-gradient(135deg,#34d399,#059669)', icon:'🖼', title:'图像生成', body:'Midjourney · Flux · GPT Image\\n尺寸 1024×1024 · 风格: 电影级', tags:['Image'], color:'#34d399' },'''
if old_defs not in html:
    print('ERROR: NODE_DEFS block not found')
else:
    html = html.replace(old_defs, new_defs)
    print('Updated NODE_DEFS tags/icons')

# 5) Adjust text toolbar vertical offset: move it closer above node (matches screenshot ~8px gap)
html = html.replace('tb.style.top = (er.top - tb.offsetHeight - 16) + \'px\';', 'tb.style.top = (er.top - tb.offsetHeight - 10) + \'px\';')
print('Adjusted text toolbar offset')

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
print('Done')
