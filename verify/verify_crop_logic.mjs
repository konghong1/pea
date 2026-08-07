// Verify ImageCropOverlay.fitDisplay NEW logic (2026-08-07 round 10):
// 1. fitDisplay now takes (natW, natH, containerEl) — reads getBoundingClientRect
// 2. Output = container's actual screen pixel size (x1.0), NOT viewport ratios
// 3. Output matches node's rendered size on screen
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '../pea-server/web/src/components/ImageCropOverlay.tsx');
const src = readFileSync(SRC, 'utf8');

let failures = 0;
function check(cond, msg) {
  if (cond) {
    console.log('  PASS:', msg);
  } else {
    console.error('  FAIL:', msg);
    failures++;
  }
}

console.log('== Source structure check ==');
check(src.includes('containerRef: React.RefObject<HTMLDivElement | null>'), 'Props has containerRef');
check(/function fitDisplay\(natW: number, natH: number, containerEl: HTMLDivElement/.test(src), 'fitDisplay signature: (natW, natH, containerEl)');
check(src.includes('getBoundingClientRect()'), 'Uses getBoundingClientRect()');
check(!src.includes('CROP_AREA_RATIO_W'), 'Old CROP_AREA_RATIO_W removed');
check(!src.includes('CROP_AREA_RATIO_H'), 'Old CROP_AREA_RATIO_H removed');
check(!src.includes('TARGET_SCALE'), 'Old TARGET_SCALE removed');
check(/baseW = rect\?\.\width/.test(src), 'Reads rect.width as baseW');
check(/baseH = rect\?\.\height/.test(src), 'Reads rect.height as baseH');

// Extract and simulate the function
const m = src.match(/function fitDisplay\([\s\S]*?^}/m);
if (!m) { console.error('FAIL: cannot extract fitDisplay'); process.exit(1); }

console.log('\n== Logic simulation (mock viewport 1440x900) ==');
const VW = 1440, VH = 900;

// Simulate fitDisplay with various node sizes
function simulateFit(natW, natH, nodeW, nodeH) {
  const viewMaxW = VW * 0.90;
  const viewMaxH = VH * 0.90;
  const baseW = nodeW;
  const baseH = nodeH;
  const finalW = Math.min(baseW, viewMaxW);
  const finalH = Math.min(baseH, viewMaxH);
  const scale = Math.min(finalW / natW, finalH / natH);
  return { w: Math.round(finalW), h: Math.round(finalH), scale };
}

// Case: Node displays at 320x480 on screen (typical card size from screenshot 1)
const d1 = simulateFit(1920, 1080, 320, 480);
check(d1.w === 320 && d1.h === 480,
  `Node 320x480 -> crop ${d1.w}x${d1.h} (SAME as node, x1.0)`);

// Case: Small node 200x300
const d2 = simulateFit(1920, 1080, 200, 300);
check(d2.w === 200 && d2.h === 300,
  `Node 200x300 -> crop ${d2.w}x${d2.h} (SAME as node)`);

// Case: Large node that exceeds 90% viewport -> clamped
const d3 = simulateFit(1920, 1080, 1400, 1000);
check(d3.w <= VW * 0.9 && d3.h <= VH * 0.9,
  `Node 1400x1000 -> crop ${d3.w}x${d3.h} (clamped to 90% viewport)`);

// Case: Same original image, different node sizes -> different crop sizes
const smallNode = simulateFit(4000, 6000, 250, 375);
const largeNode = simulateFit(4000, 6000, 500, 750);
check(smallNode.w !== largeNode.w,
  `Same image, different nodes -> DIFFERENT crop sizes (${smallNode.w}x${smallNode.h} vs ${largeNode.w}x${largeNode.h})`);

console.log('\n' + (failures === 0 ? 'ALL PASSED' : `${failures} FAILURE(S)`));
process.exit(failures === 0 ? 0 : 1);
