"""
验证 5 项 UI 改动是否正确落地。
检查项：
1. NodeChatPrompt.tsx 的 RESOLUTIONS 包含 4K
2. index.css 包含浅色模式节点文字颜色修复
3. TextNodeEditorModal.tsx 存在且被 PeaNode.tsx 引用
4. TextNodeToolbar.tsx 使用 SVG 图标
5. index.css 包含浅色模式 edge-menu 颜色修复
"""
import re, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, '..', 'pea-server', 'web', 'src')

errors = []

def check(condition, msg):
    if not condition:
        errors.append(f"  ❌ {msg}")
    else:
        print(f"  ✅ {msg}")

# ── 1. 4K 分辨率 ──
print("\n【任务1】图片画质 4K 选项")
ncp = open(os.path.join(SRC, 'components', 'NodeChatPrompt.tsx'), encoding='utf-8').read()
check("'4k'" in ncp and "4096" in ncp, "RESOLUTIONS 数组包含 4K (4096)")

# ── 2. 节点文字浅色模式 ──
print("\n【任务2】节点文字/描述浅色模式清晰度")
css = open(os.path.join(SRC, 'styles', 'index.css'), encoding='utf-8').read()
check('html:not(.dark) .pea-node-text-edit' in css, ".pea-node-text-edit 浅色模式样式存在")
check('html:not(.dark) .pea-node-generic-label' in css, ".pea-node-generic-label 浅色模式样式存在")
check('html:not(.dark) .pea-node-prompt-echo-text' in css, ".pea-node-prompt-echo-text 浅色模式样式存在")
# 验证提示词回显区使用了加深后的硬编码颜色（而非 CSS 变量）
check('#2a2a30' in css and 'prompt-echo-text' in css[css.index('#2a2a30')-200:css.index('#2a2a30')+50], "提示词回显文字使用加深色 #2a2a30")
check('#6b6b75' in css and 'prompt-echo-label' in css[css.index('#6b6b75')-200:css.index('#6b6b75')+50], "提示词标签使用加深色 #6b6b75")
check('#4a4a55' in css and 'generic-prompt' in css[css.index('#4a4a55')-200:css.index('#4a4a55')+50], "通用节点提示词使用加深色 #4a4a55")

# ── 3. 文本编辑弹窗 ──
print("\n【任务3】文本节点双击编辑弹窗")
modal_path = os.path.join(SRC, 'components', 'TextNodeEditorModal.tsx')
check(os.path.exists(modal_path), "TextNodeEditorModal.tsx 文件存在")
pn = open(os.path.join(SRC, 'components', 'PeaNode.tsx'), encoding='utf-8').read()
check("TextNodeEditorModal" in pn, "PeaNode.tsx 引用了 TextNodeEditorModal")
check("editorModalOpen" in pn, "PeaNode.tsx 使用 editorModalOpen state")
check("setEditorModalOpen(true)" in pn, "双击事件打开弹窗 (setEditorModalOpen(true))")

# ── 4. 工具栏图标化 ──
print("\n【任务4】文本节点工具栏 Markdown 功能升级")
tnt = open(os.path.join(SRC, 'components', 'TextNodeToolbar.tsx'), encoding='utf-8').read()
check('svg' in tnt.lower() and 'viewBox' in tnt, "工具栏使用 SVG 图标")
check("strikeThrough" in tnt, "包含删除线功能")
check("underline" in tnt, "包含下划线功能")
check("BLOCKQUOTE" in tnt, "包含引用块功能")
check("tnt-btn-color" in tnt, "包含颜色选择按钮")
check("tnt-color-dot" in css, "CSS 中有 .tnt-color-dot 样式")

# ── 5. 连线菜单浅色模式 ──
print("\n【任务5】连线添加节点菜单浅色模式清晰度")
check('html:not(.dark) .pea-edge-menu-item' in css, ".pea-edge-menu-item 浅色模式样式存在")
check('html:not(.dark) .pea-edge-menu-icon' in css, ".pea-edge-menu-icon 浅色模式样式存在")
check('html:not(.dark) .pea-edge-menu-label' in css, ".pea-edge-menu-label 浅色模式样式存在")
check('html:not(.dark) .pea-edge-menu-sub' in css, ".pea-edge-menu-sub 浅色模式样式存在")
check('html:not(.dark) .pea-edge-menu-tag' in css, ".pea-edge-menu-tag 浅色模式样式存在")

# ── 汇总 ──
print(f"\n{'='*50}")
if errors:
    print(f"⚠️  {len(errors)} 项检查未通过:")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("🎉 全部 20 项检查通过！所有改动已正确落地。")
    sys.exit(0)
