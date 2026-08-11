# 角度魔方功能交付概览

## 完成内容

1. **顶部功能条改名**
   - `PeaNode.tsx` 中工具条按钮由「3D」改为「角度魔方」，移除 `muted` 占桩样式，接入真实点击事件。

2. **角度魔方调整面板**
   - 新增 `src/components/AngleCubeOverlay.tsx`。
   - 面板固定定位、跟随节点锚点，支持：
     - **旋转**：-90° ~ +90°（左右旋转）
     - **倾斜**：-45° ~ +45°（上下旋转）
     - **缩放**：0 ~ 10
     - **广角镜头**：开关
     - **重置**：一键回到初始参数
   - 左侧面板实时预览图片随参数做 3D 变换。
   - 底部显示当前模型生成 1 张图的预估消耗（固定 `n=1`）。

3. **生成与建节点**
   - 点击发送后：
     - 解析当前图片为可外传参考图 URL（与节点聊天提交同一套规则）。
     - 构造多角度生成 prompt，调用 `acceptNodeGenerationJob({ type: 'image', n: 1, reference_images: [url], model })`。
     - 余额消耗由服务端按 `n=1` 权威计价，前端不指定金额。
     - 在当前节点右侧创建 `label: '多角度'` 的新图片节点，并自动连边；新节点进入生成态，通过 `registerJob` + `pollNodeJobResult` 等待结果回填。

4. **样式**
   - `src/styles/index.css` 新增 `.pea-angle-cube-*` 系列样式，适配深色/浅色主题。

## 验证

- `npm run typecheck` 通过
- `npm run build` 通过

## 相关文件

- `pea-server/web/src/components/AngleCubeOverlay.tsx`
- `pea-server/web/src/components/PeaNode.tsx`
- `pea-server/web/src/styles/index.css`
