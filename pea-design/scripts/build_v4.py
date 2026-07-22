# -*- coding: utf-8 -*-
"""整合脚本：基于 pea-canvas-v3.html 出 v4 版本
- 把电商套图(ecommerce-gallery-latest.html)融入，导航插入在工作空间与TapTV之间
- 电商套图 CSS 加 #page-ecom 作用域前缀(避免污染 pea 全局)，视觉与功能逻辑保留
- 补全账户设置(个人资料/账户设置/订阅管理)，映射到 creator/profile 接口数据
"""
import re

TN = r"D:/workspace/ai-agent/pea-canvas-v3.html"
EG = r"D:/workspace/ai-agent/designs/ecommerce-gallery-latest.html"
OUT = r"D:/workspace/ai-agent/pea-canvas-v4.html"

tn = open(TN, encoding="utf-8").read()
eg = open(EG, encoding="utf-8").read()

# ---------- 提取电商套图三段 ----------
m = re.search(r"<style>(.*?)</style>", eg, re.S)
eg_css = m.group(1)
m = re.search(r"<body>(.*?)<script>", eg, re.S)
eg_body = m.group(1)
m = re.search(r"<script>(.*?)</script>", eg, re.S)
eg_js = m.group(1)

# ---------- 电商套图 CSS 加 #page-ecom 作用域前缀 ----------
def scope_css(css):
    out = []
    stack = []  # 记录 at-rule 类型，用于排除 @keyframes 内部
    for line in css.split("\n"):
        s = line.strip()
        if not s:
            out.append(line); continue
        if ":root" in line:           # 变量保持全局(与 pea 无重名)
            out.append(line); continue
        ob = s.count("{"); cb = s.count("}")
        if s.startswith("@"):
            if "keyframes" in s: stack.append("keyframes")
            elif "media" in s: stack.append("media")
            elif "font-face" in s: stack.append("fontface")
            elif "supports" in s: stack.append("supports")
            out.append(line)
            if ob - cb <= 0 and stack:   # 单行 @keyframes{...} 自行闭合
                stack.pop()
            continue
        if cb > 0 and ob == 0:          # 关闭括号行
            for _ in range(min(cb, len(stack))):
                stack.pop()
            out.append(line); continue
        if ob > 0:                      # 规则声明行
            in_kf = bool(stack) and stack[-1] == "keyframes"
            if in_kf:
                out.append(line); continue
            idx = line.index("{")
            sel = line[:idx]; rest = line[idx:]
            sels = [x.strip() for x in sel.split(",")]
            newsel = ", ".join("#page-ecom " + x for x in sels if x)
            out.append(newsel + " " + rest)
        else:
            out.append(line)
    return "\n".join(out)

eg_css_scoped = scope_css(eg_css)
# 顶部偏移 60px(电商套图自带 topbar) -> 52px(pea topbar)，对齐
eg_css_scoped = eg_css_scoped.replace("calc(100vh - 60px)", "calc(100vh - 52px)")
eg_css_scoped = eg_css_scoped.replace("calc(100vh-60px)", "calc(100vh-52px)")
eg_css_scoped = eg_css_scoped.replace("top: 60px", "top: 52px").replace("top:60px", "top: 52px")
# #page-ecom 激活时占满 topbar 以下区域，浅色背景，内部各自滚动
eg_css_scoped += (
    "\n/* v4: 电商套图页面容器定位(对齐 pea topbar) */\n"
    "#page-ecom.page.active{position:fixed;inset:0;top:52px;overflow:hidden;background:var(--bg);}\n"
)

# ---------- 电商套图 body：去掉自带 header.topbar，包裹 #page-ecom ----------
eg_body = re.sub(r"<header class=\"topbar\">.*?</header>", "", eg_body, flags=re.S)
eg_page = '<div id="page-ecom" class="page">\n' + eg_body.strip() + "\n</div>"

# ---------- 电商套图 JS：overflow 限定到 #page-ecom，避免干扰 pea body ----------
eg_js = eg_js.replace(
    "document.body.style.overflow",
    "document.getElementById('page-ecom').style.overflow",
)

# ================= 账户设置增补(pea 深色风格) =================
acct_css = """
/* ═══ ACCOUNT SETTINGS DRAWER (v4 新增) ═══ */
.acct-scrim{position:fixed;inset:0;background:rgba(0,0,0,.5);backdrop-filter:blur(3px);z-index:150;opacity:0;pointer-events:none;transition:.2s ease;}
.acct-scrim.open{opacity:1;pointer-events:auto;}
.acct-drawer{position:fixed;top:0;right:0;height:100vh;width:min(460px,94vw);background:var(--bg-surface);border-left:1px solid var(--border);box-shadow:var(--shadow-md);z-index:160;transform:translateX(100%);transition:transform .26s ease;display:flex;flex-direction:column;}
.acct-drawer.open{transform:translateX(0);}
.acct-head{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border);}
.acct-title{font-size:15px;font-weight:700;}
.acct-close{width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:16px;transition:.15s ease;}
.acct-close:hover{background:var(--bg-hover);color:var(--text-primary);}
.acct-tabs{display:flex;gap:4px;padding:12px 20px 0;border-bottom:1px solid var(--border);}
.acct-tab{font-size:13px;padding:8px 14px;border-radius:8px 8px 0 0;color:var(--text-secondary);transition:.15s ease;cursor:pointer;border-bottom:2px solid transparent;}
.acct-tab.active{color:var(--accent);border-bottom-color:var(--accent);}
.acct-body{flex:1;overflow-y:auto;padding:20px;}
.acct-field{margin-bottom:16px;}
.acct-field label{display:block;font-size:12px;color:var(--text-secondary);margin-bottom:6px;}
.acct-input{width:100%;background:var(--bg-elevated);border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-size:13px;color:var(--text-primary);outline:none;transition:.15s ease;}
.acct-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow);}
.acct-hint{font-size:11px;color:var(--text-muted);margin-top:5px;line-height:1.5;}
.acct-avatar-row{display:flex;align-items:center;gap:12px;margin-bottom:18px;}
.acct-avatar{width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,#667eea,#764ba2);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:700;color:#fff;}
.acct-save{width:100%;padding:11px;border-radius:8px;background:var(--accent);color:#fff;font-size:13px;font-weight:600;margin-top:8px;transition:.15s ease;}
.acct-save:hover{background:var(--accent-hover);}
.acct-sub-card{background:var(--bg-elevated);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:12px;}
.acct-sub-plan{font-size:16px;font-weight:700;margin-bottom:4px;}
.acct-sub-meta{font-size:12px;color:var(--text-secondary);}
.acct-stat-row{display:flex;justify-content:space-around;text-align:center;padding:8px 0;}
.acct-stat-num{font-size:20px;font-weight:800;color:var(--accent);}
.acct-stat-lbl{font-size:11px;color:var(--text-muted);}
"""

acct_html = """
<!-- ═══ ACCOUNT CENTER DRAWER (v4 新增) ═══ -->
<div class="acct-scrim" id="acctScrim" onclick="closeAccountSettings()"></div>
<aside class="acct-drawer" id="acctDrawer">
  <div class="acct-head">
    <div class="acct-title">账户中心</div>
    <button class="acct-close" onclick="closeAccountSettings()">✕</button>
  </div>
  <div class="acct-tabs">
    <div class="acct-tab active" data-atab="profile" onclick="switchAcctTab('profile',this)">👤 个人资料</div>
    <div class="acct-tab" data-atab="settings" onclick="switchAcctTab('settings',this)">⚙️ 账户设置</div>
    <div class="acct-tab" data-atab="sub" onclick="switchAcctTab('sub',this)">💎 订阅管理</div>
  </div>
  <div class="acct-body">
    <div id="acctTab-profile">
      <div class="acct-avatar-row">
        <div class="acct-avatar" id="acctAvatar">W</div>
        <div>
          <div style="font-size:14px;font-weight:600" id="acctUname">wah1763751448</div>
          <div style="font-size:12px;color:var(--text-muted)" id="acctMail">wah1763751448@163.com</div>
        </div>
      </div>
      <div class="acct-field"><label>昵称</label><input class="acct-input" id="fNick" value="wah1763751448"></div>
      <div class="acct-field"><label>邮箱</label><input class="acct-input" id="fEmail" value="wah1763751448@163.com"></div>
      <div class="acct-field"><label>简介</label><textarea class="acct-input" id="fBio" rows="3">I am turning imagination into reality.</textarea></div>
      <button class="acct-save" onclick="saveAccount('profile')">保存个人资料</button>
    </div>
    <div id="acctTab-settings" style="display:none">
      <div class="acct-field"><label>职业</label><input class="acct-input" id="fOcc" placeholder="如：电商设计师"></div>
      <div class="acct-field"><label>国家 / 地区</label><div style="display:flex;gap:8px"><input class="acct-input" id="fCountry" placeholder="国家"><input class="acct-input" id="fCity" placeholder="城市"></div></div>
      <div class="acct-field"><label>社交链接（JSON，可选）</label><input class="acct-input" id="fSocial" placeholder='{"twitter":"","weibo":""}'></div>
      <div class="acct-hint">以上信息用于完善你的创作者主页，保存后将在 pea 社区同步显示。</div>
      <button class="acct-save" onclick="saveAccount('settings')">保存设置</button>
    </div>
    <div id="acctTab-sub" style="display:none">
      <div class="acct-sub-card">
        <div class="acct-sub-plan">🎁 免费版</div>
        <div class="acct-sub-meta">当前套餐：Free · 积分余额 <b id="acctPoints">200</b></div>
      </div>
      <div class="acct-stat-row">
        <div><div class="acct-stat-num">0</div><div class="acct-stat-lbl">作品</div></div>
        <div><div class="acct-stat-num">0</div><div class="acct-stat-lbl">关注者</div></div>
        <div><div class="acct-stat-num">0</div><div class="acct-stat-lbl">关注中</div></div>
      </div>
      <button class="acct-save" onclick="toast('已为你打开会员升级页 💎')">升级会员</button>
    </div>
  </div>
</aside>
"""

acct_js = """
/* ═══ ACCOUNT SETTINGS (v4 新增) ═══ */
function openAccountSettings(tab){
  document.getElementById('acctScrim').classList.add('open');
  document.getElementById('acctDrawer').classList.add('open');
  var el=document.querySelector('.acct-tab[data-atab="'+(tab||'profile')+'"]');
  switchAcctTab(tab||'profile', el);
}
function closeAccountSettings(){
  document.getElementById('acctScrim').classList.remove('open');
  document.getElementById('acctDrawer').classList.remove('open');
}
function switchAcctTab(tab, el){
  document.querySelectorAll('.acct-tab').forEach(function(t){t.classList.remove('active');});
  if(el) el.classList.add('active');
  document.getElementById('acctTab-profile').style.display = tab==='profile'?'':'none';
  document.getElementById('acctTab-settings').style.display = tab==='settings'?'':'none';
  document.getElementById('acctTab-sub').style.display = tab==='sub'?'':'none';
}
function saveAccount(which){
  if(which==='profile'){
    var nick=document.getElementById('fNick').value.trim();
    var mail=document.getElementById('fEmail').value.trim();
    var bio=document.getElementById('fBio').value.trim();
    if(nick) document.getElementById('acctUname').textContent=nick;
    if(mail) document.getElementById('acctMail').textContent=mail;
    var av=document.getElementById('acctAvatar'); if(nick) av.textContent=nick.charAt(0).toUpperCase();
    toast('个人资料已保存 ✓');
  } else {
    toast('账户设置已保存 ✓');
  }
  closeAccountSettings();
}
"""

# ================= 组装 v4 =================
# 1) 注入 CSS(电商套图作用域 + 账户设置)
tn = tn.replace("</style>", eg_css_scoped + "\n" + acct_css + "</style>", 1)

# 2) 导航插入电商套图按钮(工作空间 canvas 与 TapTV community 之间)
tn = tn.replace(
    '<button class="nav-item" data-page="community" onclick="switchPage(\'community\')">📺 TapTV</button>',
    '<button class="nav-item" data-page="community" onclick="switchPage(\'community\')">📺 TapTV</button>\n    <button class="nav-item" data-page="ecom" onclick="switchPage(\'ecom\')">🛍️ 电商套图</button>',
    1,
)

# 3) body 内插入 电商套图页面 + 账户设置抽屉(在 <script> 之前)
tn = tn.replace("<script>", eg_page + "\n" + acct_html + "\n<script>", 1)

# 4) 账户菜单项：toast 占位 -> 真实功能
tn = tn.replace(
    '<div class="ctx-item" onclick="toast(\'设置 ⚙️\');closePopups()">⚙️ 设置</div>',
    '<div class="ctx-item" onclick="openAccountSettings(\'settings\');closePopups()">⚙️ 设置</div>',
    1,
)
tn = tn.replace(
    '<div class="ctx-item" onclick="toast(\'个人资料 👤\');closePopups()">👤 个人资料</div>',
    '<div class="ctx-item" onclick="openAccountSettings(\'profile\');closePopups()">👤 个人资料</div>',
    1,
)
tn = tn.replace(
    '<div class="ctx-item" onclick="toast(\'订阅管理 💎\');closePopups()">💎 订阅管理</div>',
    '<div class="ctx-item" onclick="openAccountSettings(\'sub\');closePopups()">💎 订阅管理</div>',
    1,
)

# 5) 注入 JS(电商套图逻辑 + 账户设置逻辑)，合并进原 script 块末尾
tn = tn.replace("</script>", eg_js + "\n" + acct_js + "</script>", 1)

open(OUT, "w", encoding="utf-8").write(tn)
print("OK ->", OUT, "bytes:", len(tn))
