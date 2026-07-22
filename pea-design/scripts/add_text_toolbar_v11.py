import re

path = 'pea-canvas-v11.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1) Add floating text toolbar HTML after canvas area
old_canvas_end = '''  </div>
</div>

<!-- Right Inspector Panel -->'''
new_canvas_end = '''  </div>
</div>

<!-- Floating Text Node Toolbar (matches pea screenshot) -->
<div class="text-node-toolbar" id="textNodeToolbar" style="display:none;">
  <div class="tnt-bar">
    <button class="tnt-color" title="颜色"></button>
    <div class="tnt-sep"></div>
    <button class="tnt-btn active" title="Heading 1">H1</button>
    <button class="tnt-btn" title="Heading 2">H2</button>
    <button class="tnt-btn" title="Heading 3">H3</button>
    <button class="tnt-btn" title="Paragraph">¶</button>
    <div class="tnt-sep"></div>
    <button class="tnt-btn" title="Bold">B</button>
    <button class="tnt-btn" title="Italic">I</button>
    <button class="tnt-btn" title="Bullet list">≡</button>
    <button class="tnt-btn" title="Align">☰</button>
    <button class="tnt-btn" title="Divider">−</button>
    <button class="tnt-btn" title="Emoji">☺</button>
    <button class="tnt-btn" title="Image">🖼</button>
    <button class="tnt-btn" title="Link">🔗</button>
    <button class="tnt-btn" title="Expand">⛶</button>
  </div>
  <div class="tnt-label">Text</div>
</div>

<!-- Right Inspector Panel -->'''

if old_canvas_end in content:
    content = content.replace(old_canvas_end, new_canvas_end)
    print('toolbar HTML added')
else:
    print('canvas end marker NOT FOUND')

# 2) Add CSS for text toolbar after add-pal-send:hover
old_css_end = '''.add-pal-send:hover{ transform:scale(1.06); box-shadow:0 4px 16px rgba(31,162,220,.4); }
'''
new_css = '''.add-pal-send:hover{ transform:scale(1.06); box-shadow:0 4px 16px rgba(31,162,220,.4); }

/* ── FLOATING TEXT NODE TOOLBAR ── */
.text-node-toolbar{
  position:absolute; z-index:120;
  left:50%; transform:translateX(-50%);
  display:flex; flex-direction:column; align-items:center; gap:6px;
  pointer-events:none; filter:drop-shadow(0 8px 24px rgba(0,0,0,.45));
}
.tnt-bar{
  display:flex; align-items:center; gap:4px;
  background:#1e1e1e; border:1px solid rgba(255,255,255,.08);
  border-radius:999px; padding:5px 8px; pointer-events:auto;
}
.tnt-color{
  width:22px; height:22px; border-radius:50%; border:1px solid rgba(255,255,255,.2);
  background:#fff; cursor:pointer; padding:0; flex-shrink:0;
}
.tnt-sep{ width:1px; height:18px; background:rgba(255,255,255,.10); margin:0 2px; }
.tnt-btn{
  width:26px; height:26px; border-radius:6px; border:none; background:transparent;
  color:#9ca3af; font-size:12px; font-weight:500; cursor:pointer; transition:.12s;
  display:flex; align-items:center; justify-content:center; flex-shrink:0;
}
.tnt-btn:hover{ background:rgba(255,255,255,.08); color:#e5e7eb; }
.tnt-btn.active{ background:rgba(255,255,255,.12); color:#fff; }
.tnt-label{
  font-size:11px; color:#9ca3af; letter-spacing:.2px; background:rgba(0,0,0,.45);
  padding:2px 8px; border-radius:10px;
}
'''
if old_css_end in content:
    content = content.replace(old_css_end, new_css)
    print('toolbar CSS added')
else:
    print('CSS insertion marker NOT FOUND')

# 3) Add JS to position toolbar after renderNodes and on selection
old_render_end = '''  const hint = document.getElementById('canvasHint');
  if(hint) hint.style.display = state.nodes.length ? 'none' : 'flex';
}'''
new_render_end = '''  const hint = document.getElementById('canvasHint');
  if(hint) hint.style.display = state.nodes.length ? 'none' : 'flex';
  updateTextToolbar();
}'''
if old_render_end in content:
    content = content.replace(old_render_end, new_render_end)
    print('renderNodes hook added')
else:
    print('renderNodes hook marker NOT FOUND')

# Add updateTextToolbar function before drawConnections or at end of nodes section
old_func_marker = '''/* ═══════════════════════════════════════════\n   DRAW CONNECTIONS (bezier, viewport coords)'''
new_func = '''function updateTextToolbar(){
  const tb = document.getElementById('textNodeToolbar');
  if(!tb) return;
  const selIds = [...state.sel];
  if(selIds.length===1){
    const node = state.nodes.find(n=>n.id===selIds[0]);
    if(node && node.type==='text'){
      const el = document.getElementById(node.id);
      if(el){
        const wrap = document.getElementById('canvasArea');
        const r = wrap.getBoundingClientRect();
        const er = el.getBoundingClientRect();
        tb.style.display = 'flex';
        tb.style.top = (er.top - r.top - tb.offsetHeight - 12) + 'px';
        tb.style.left = (er.left - r.left + er.width/2) + 'px';
        return;
      }
    }
  }
  tb.style.display = 'none';
}

/* ═══════════════════════════════════════════\n   DRAW CONNECTIONS (bezier, viewport coords)'''
if old_func_marker in content:
    content = content.replace(old_func_marker, new_func)
    print('updateTextToolbar added')
else:
    print('function insertion marker NOT FOUND')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
