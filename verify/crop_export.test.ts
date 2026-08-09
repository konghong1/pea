// 裁剪导出（超采样 / 防模糊）单测
// 直接 import 生产源码 pea-server/web/src/components/cropExport，不复制逻辑，
// 避免测试与实现双写漂移。
//
// 运行：node verify/run-ts-tests.mjs      （或 CI 里的 web job）
//
// 这组测试把「裁图不模糊」从主观感受钉成可断言的不变量：
//   - 导出必须从原图真实像素采样（不是从预览图）
//   - 必须按 DPR 超采样，绝不能退回 1:1 导出（历史 bug 回归点）
//   - 超采样不得撑爆 canvas 面积上限（Safari/iOS 会静默出空白图）
//   - 源区域本身低清时必须诚实标记，而不是假装清晰
import {
  mapCropToSource,
  resolveExportScale,
  computeCropExportPlan,
  assessDisplaySharpness,
  MAX_EXPORT_SCALE,
  MAX_OUTPUT_PIXELS,
  LOW_RES_SOURCE_PX,
} from '../pea-server/web/src/components/cropExport';

let failures = 0;
function check(cond: boolean, msg: string) {
  if (cond) {
    console.log('  PASS  ', msg);
  } else {
    console.error('  FAIL  ', msg);
    failures++;
  }
}
function approx(a: number, b: number, eps = 1e-6) {
  return Math.abs(a - b) <= eps;
}

// ─────────────────────────────────────────────────────────────────────────────
console.log('— mapCropToSource：flow 坐标 → 原图真实像素 —');

// 原图 4000×3000，舞台按 400×300 显示（缩放 1/10）
const NAT = { w: 4000, h: 3000 };
const DISP = { w: 400, h: 300 };

let src = mapCropToSource({ x: 100, y: 60, w: 200, h: 150 }, DISP, NAT);
check(approx(src.sx, 1000), `sx: 100 flow → ${src.sx} 原图px（×10）`);
check(approx(src.sy, 600), `sy: 60 flow → ${src.sy} 原图px`);
check(approx(src.sw, 2000), `sw: 200 flow → ${src.sw} 原图px（关键：乘不是除）`);
check(approx(src.sh, 1500), `sh: 150 flow → ${src.sh} 原图px`);

// 越界钳制：drawImage 读到图像外会画出透明边
src = mapCropToSource({ x: 350, y: 250, w: 200, h: 200 }, DISP, NAT);
check(
  src.sx + src.sw <= NAT.w + 1e-6 && src.sy + src.sh <= NAT.h + 1e-6,
  `右下越界被钳制在原图内: sx+sw=${src.sx + src.sw} <= ${NAT.w}`,
);
src = mapCropToSource({ x: -50, y: -50, w: 100, h: 100 }, DISP, NAT);
check(src.sx === 0 && src.sy === 0, `左上负坐标钳制到 0: (${src.sx}, ${src.sy})`);

// 退化输入不应产生 NaN（disp 未测量完成时可能为 0）
src = mapCropToSource({ x: 10, y: 10, w: 10, h: 10 }, { w: 0, h: 0 }, NAT);
check(
  Number.isFinite(src.sw) && Number.isFinite(src.sh) && src.sw === 0,
  `disp=0 不产生 NaN，安全返回空矩形`,
);

// ─────────────────────────────────────────────────────────────────────────────
console.log('\n— resolveExportScale：超采样倍率 —');

check(resolveExportScale(1) === 1, 'DPR 1 → 1×');
check(resolveExportScale(1.5) === 1.5, 'DPR 1.5 → 1.5×（跟随设备）');
check(resolveExportScale(2) === 2, 'DPR 2 → 2×');
check(resolveExportScale(3) === MAX_EXPORT_SCALE, `DPR 3 → 封顶 ${MAX_EXPORT_SCALE}×（防内存爆炸）`);
check(resolveExportScale(0.5) === 1, 'DPR 0.5 → 提升到 1×（永不缩小导出）');
check(resolveExportScale(0) === 1, 'DPR 0 → 安全回退 1×');
check(resolveExportScale(NaN) === 1, 'DPR NaN → 安全回退 1×');
check(resolveExportScale(undefined) === 1, 'DPR undefined（非浏览器环境）→ 1×');

// ─────────────────────────────────────────────────────────────────────────────
console.log('\n— computeCropExportPlan：导出方案 —');

// 常规：4000×3000 原图裁中间一块，DPR2 → 应 2× 超采样
let plan = computeCropExportPlan({
  crop: { x: 100, y: 60, w: 200, h: 150 },
  disp: DISP,
  nat: NAT,
  dpr: 2,
});
check(plan.status === 'ok', `status = ok`);
check(plan.exportScale === 2, `exportScale = ${plan.exportScale}`);
check(plan.outWidth === 4000 && plan.outHeight === 3000, `输出 ${plan.outWidth}×${plan.outHeight}（源 2000×1500 的 2×）`);
check(!plan.lowResSource, '源区域 2000px，不触发低清告警');
check(!plan.downscaledForLimit, '未触碰面积上限');

// ★ 历史 bug 回归点：绝不能退回 1:1 导出
check(
  plan.outWidth > plan.source.sw,
  `回归钉死：输出像素 ${plan.outWidth} > 源区域 ${plan.source.sw}，未退回 1:1 导出`,
);

// DPR1 设备：1× 导出，尺寸等于源区域真实像素
plan = computeCropExportPlan({ crop: { x: 100, y: 60, w: 200, h: 150 }, disp: DISP, nat: NAT, dpr: 1 });
check(plan.outWidth === 2000 && plan.outHeight === 1500, `DPR1 → ${plan.outWidth}×${plan.outHeight}（源真实像素 1:1，非预览尺寸）`);

// 无效裁剪
plan = computeCropExportPlan({ crop: { x: 0, y: 0, w: 0.05, h: 0.05 }, disp: DISP, nat: NAT, dpr: 2 });
check(plan.status === 'too-small', `极小裁剪 → status = ${plan.status}，调用方应中止`);

// 低清源告警：原图 400×300 显示 400×300（1:1），裁 150×100 的小块
plan = computeCropExportPlan({
  crop: { x: 0, y: 0, w: 150, h: 100 },
  disp: { w: 400, h: 300 },
  nat: { w: 400, h: 300 },
  dpr: 2,
});
check(
  plan.lowResSource,
  `源区域 ${plan.source.sw}×${plan.source.sh} < ${LOW_RES_SOURCE_PX}px → 触发低清告警（前端救不了，需高清源或 AI 超分）`,
);
check(plan.status === 'ok', '低清但仍可导出（告警而非阻断）');

// ─────────────────────────────────────────────────────────────────────────────
console.log('\n— canvas 面积上限兜底（Safari/iOS 空白图防护）—');

// 8000×6000 原图整幅裁剪，DPR2 若不兜底 → 16000×12000 = 1.92 亿 px，必炸
plan = computeCropExportPlan({
  crop: { x: 0, y: 0, w: 800, h: 600 },
  disp: { w: 800, h: 600 },
  nat: { w: 8000, h: 6000 },
  dpr: 2,
});
const outPixels = plan.outWidth * plan.outHeight;
check(plan.downscaledForLimit, '触碰上限时标记 downscaledForLimit');
check(
  outPixels <= MAX_OUTPUT_PIXELS,
  `输出 ${plan.outWidth}×${plan.outHeight} = ${(outPixels / 1e6).toFixed(1)}M px <= 上限 ${(MAX_OUTPUT_PIXELS / 1e6).toFixed(1)}M px`,
);
check(plan.exportScale < 2, `倍率自动回退到 ${plan.exportScale.toFixed(3)}×，出图而非空白`);
check(
  Math.abs(plan.outWidth / plan.outHeight - 8000 / 6000) < 0.01,
  `降级后仍保持宽高比 ${(plan.outWidth / plan.outHeight).toFixed(3)} ≈ 1.333`,
);

// 刚好不触限的场景不应被误降级
plan = computeCropExportPlan({
  crop: { x: 0, y: 0, w: 100, h: 100 },
  disp: { w: 100, h: 100 },
  nat: { w: 1000, h: 1000 },
  dpr: 2,
});
check(!plan.downscaledForLimit && plan.exportScale === 2, '2000×2000 = 4M px 未触限，保持 2×');

// ─────────────────────────────────────────────────────────────────────────────
console.log('\n— assessDisplaySharpness：会不会糊的判定 —');

let v = assessDisplaySharpness(4000, 400, 2);
check(v.sharp, `4000px 位图 @ 400css×DPR2(=800物理px) → sharp, ratio=${v.ratio.toFixed(2)}`);

v = assessDisplaySharpness(150, 280, 1);
check(!v.sharp, `150px 位图 @ 280css×DPR1 → 会糊, ratio=${v.ratio.toFixed(2)}（低清源的真实处境）`);

v = assessDisplaySharpness(800, 400, 2);
check(v.sharp && approx(v.ratio, 1), `恰好 1:1 物理像素 → sharp, ratio=${v.ratio.toFixed(2)}（临界值判定为清晰）`);

v = assessDisplaySharpness(799, 400, 2);
check(!v.sharp, `少 1px 即判定会糊 ratio=${v.ratio.toFixed(4)}（阈值严格，不放水）`);

// ─────────────────────────────────────────────────────────────────────────────
console.log('\n— 端到端场景：用户的「把大图截成小图」—');

// 场景 A：高清源 6000×4000，裁出 1/10 区域，节点显示 320px 宽，DPR2
plan = computeCropExportPlan({
  crop: { x: 0, y: 0, w: 60, h: 40 },
  disp: { w: 600, h: 400 },
  nat: { w: 6000, h: 4000 },
  dpr: 2,
});
v = assessDisplaySharpness(plan.outWidth, 320, 2);
check(
  v.sharp,
  `高清源裁小块 → 导出 ${plan.outWidth}px，节点 320css@DPR2 显示 → 清晰 (ratio=${v.ratio.toFixed(2)})`,
);

// 场景 B：源图本身就小 800×600，裁出一小块，节点仍显示 320px → 物理上救不回来
plan = computeCropExportPlan({
  crop: { x: 0, y: 0, w: 120, h: 90 },
  disp: { w: 800, h: 600 },
  nat: { w: 800, h: 600 },
  dpr: 2,
});
v = assessDisplaySharpness(plan.outWidth, 320, 2);
check(
  plan.lowResSource && !v.sharp,
  `低清源裁小块 → 导出 ${plan.outWidth}px vs 需要 ${v.requiredPhysicalPx}px → 仍会糊且已告警（诚实，不假装）`,
);

// 场景 C：同一低清源，但节点显示得小一点 → 就清晰了（证明糊是"相对"的）
v = assessDisplaySharpness(plan.outWidth, 100, 2);
check(v.sharp, `同一位图缩到 100css 显示 → 清晰 (ratio=${v.ratio.toFixed(2)})，证明模糊是显示尺寸的相对概念`);

console.log('\n' + (failures === 0 ? '✅ ALL PASS' : `❌ ${failures} FAILED`));
if (failures > 0) process.exit(1);
