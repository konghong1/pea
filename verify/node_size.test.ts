// 节点尺寸与比例单测：验证上传图片后节点框按真实比例自适应的计算基础
import { getNodeSize, simplifyRatio, LONG_EDGE } from '../pea-server/web/src/lib/nodeSize';

let failures = 0;
function check(cond: boolean, msg: string) {
  if (cond) {
    console.log('  PASS  ', msg);
  } else {
    console.error('  FAIL  ', msg);
    failures++;
  }
}

console.log('— simplifyRatio：浮点宽高 → 最简整数比 —');
check(simplifyRatio(1920, 1080) === '16:9', `1920×1080 → ${simplifyRatio(1920, 1080)}`);
check(simplifyRatio(1080, 1920) === '9:16', `1080×1920 → ${simplifyRatio(1080, 1920)}`);
check(simplifyRatio(1000, 1000) === '1:1', `1000×1000 → ${simplifyRatio(1000, 1000)}`);
check(simplifyRatio(800, 600) === '4:3', `800×600 → ${simplifyRatio(800, 600)}`);
check(simplifyRatio(600, 800) === '3:4', `600×800 → ${simplifyRatio(600, 800)}`);
check(simplifyRatio(1280, 720) === '16:9', `1280×720 → ${simplifyRatio(1280, 720)}`);

console.log('— getNodeSize：最长边恒定 + 比例决定宽高 —');
// 竖屏 9:16：高为长边
check(
  getNodeSize('9:16', 'image').width === Math.round(LONG_EDGE * (9 / 16)) && getNodeSize('9:16', 'image').height === LONG_EDGE,
  `9:16 → 宽 ${getNodeSize('9:16', 'image').width}、高 ${LONG_EDGE}`
);
// 横屏 16:9：宽为长边
check(
  getNodeSize('16:9', 'image').width === LONG_EDGE && getNodeSize('16:9', 'image').height === Math.round(LONG_EDGE * (9 / 16)),
  `16:9 → 宽 ${LONG_EDGE}、高 ${getNodeSize('16:9', 'image').height}`
);
// 方形 1:1
check(
  getNodeSize('1:1', 'text').width === LONG_EDGE && getNodeSize('1:1', 'text').height === LONG_EDGE,
  `1:1 → 宽高均为 ${LONG_EDGE}`
);
// kind 默认回退：image 默认 9:16
check(
  getNodeSize(undefined, 'image').height === LONG_EDGE,
  `image 无 aspectRatio 时默认高为长边（9:16）`
);
// 非法比例回退 1:1
check(
  getNodeSize('abc', 'image').width === LONG_EDGE && getNodeSize('abc', 'image').height === LONG_EDGE,
  `非法比例回退 1:1`
);

if (failures > 0) {
  console.error(`\n✗ ${failures} 项断言失败`);
  process.exit(1);
} else {
  console.log('\n✅ ALL PASS');
}
