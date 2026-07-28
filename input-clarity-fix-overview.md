# 节点编辑框清晰度优化报告

## 问题现象
用户在 `NodeChatPrompt` 编辑框输入内容时，反馈输入框整体「灰蒙蒙」，由文字与 `@` 引用图片 chip 拼成的句子看起来不够清晰。

## 根因分析
检查 `pea-server/web/src/styles/index.css` 中编辑框相关样式，发现几个导致「雾感」与低对比度的点：

1. **容器背景过透**：`.node-input-bar` 背景 `rgba(28,28,34,0.96)` + `backdrop-filter: blur(14px)`，在深色画布上会显得发灰、不够扎实。
2. **文字偏细偏小**：`.node-prompt-editor` 为 `13px / font-weight: 400`，在深色半透明背景上笔画容易发虚。
3. **占位符与正文对比不足**：占位符 `rgba(255,255,255,0.45)`，与正文 `#fff` 差距不够大，用户输入后仍可能带有「占位符感」。
4. **`@` 引用 chip 太淡**：图片/文本 token 背景仅 `rgba(31,162,220,0.18)`、边框 `0.28`，在深色输入框里几乎融进背景，导致整行文字被「切碎」且不够清晰。

## 改动内容
文件：`pea-server/web/src/styles/index.css`

### 1. 降低输入栏雾感
```css
.node-input-bar {
  background: rgba(28, 28, 34, 0.98);          /* 0.96 → 0.98 */
  border: 1px solid rgba(255, 255, 255, 0.12); /* 0.08 → 0.12 */
  box-shadow:
    0 18px 40px rgba(0, 0, 0, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);  /* 新增顶部内高光 */
  backdrop-filter: blur(14px) saturate(120%);  /* 增加一点点饱和度 */
}
```

### 2. 提升正文清晰度
```css
.node-prompt-editor {
  font-size: 14px;        /* 13px → 14px */
  font-weight: 450;       /* 默认 400 → 450，笔画更扎实 */
  letter-spacing: 0.01em; /* 微扩字距，提升可读性 */
  line-height: 1.65;      /* 1.6 → 1.65 */
  caret-color: var(--pea-brand); /* 光标用品牌蓝，更醒目 */
}
```

### 3. 拉開占位符与正文对比
```css
.node-prompt-editor:empty::before {
  color: rgba(255, 255, 255, 0.36); /* 0.45 → 0.36 */
}
```

### 4. 强化 `@` 引用 chip
```css
.node-prompt-editor .pea-ref {
  background: rgba(31, 162, 220, 0.26); /* 0.18 → 0.26 */
  border: 1px solid rgba(31, 162, 220, 0.45); /* 0.28 → 0.45 */
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);  /* 新增投影 */
}
.node-prompt-editor .pea-ref-text {
  color: #fff;        /* 0.92 → 1 */
  font-weight: 500;   /* 文本引用加粗 */
}
.node-prompt-editor .pea-ref-thumb {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12); /* 图片 chip 内描边 */
}
```

## 验证
- `npm run build` 通过（仅既有 chunk 体积告警）。
- 已将 `web/dist/` 复制到 `pea-server-web-1` 容器并 reload nginx，改动已生效到线上容器。

## 建议后续团队规范
1. 深色半透明面板避免低于 `0.96` 的背景透明度，必要时用 inset 高光增加层次。
2. 小字号文本在深色背景上建议 `font-weight >= 450`，避免发虚。
3. 占位符与正文的透明度差建议 `>= 0.55`，让二者一眼可区分。
4. 内联 token/chip 的彩色背景不要低于 `0.22`，边框不要低于 `0.4`，否则在深色背景上会被「吃掉」。
