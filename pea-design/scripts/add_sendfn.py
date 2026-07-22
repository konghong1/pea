with open('pea-canvas-v8.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Insert sendFromWorkspace after sendAgent's closing brace
marker = """  }, 900);
}
function agentReply(v){"""

new_code = """  }, 900);
}
function sendFromWorkspace(){
  const ta=document.getElementById('wsInput'); const v=ta.value.trim(); if(!v) return;
  ta.value=''; toast('已发送到 Agent: '+v);
  // Also push to right-panel chat for continuity
  chatLog.push({ who:'你', role:'user', text:v });
  switchRPTab('chat');
  typing=true; renderInspector();
  setTimeout(()=>{
    typing=false;
    chatLog.push({ who:'pea Agent', role:'agent', text: agentReply(v) });
    renderInspector();
  }, 900);
}
function agentReply(v){"""

if marker in content:
    content = content.replace(marker, new_code)
    with open('pea-canvas-v8.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK — sendFromWorkspace added')
else:
    print('ERROR: marker not found')
