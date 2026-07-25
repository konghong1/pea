import EcommerceGallery from '../ecom/EcommerceGallery';
// 全局导入电商套图设计系统（含 pea 适配品牌色 Token）
import '../ecom/gallery-design-system.css';

/** 电商套图 —— 完整模块（原版 ai-agent EcommerceGallery 迁移，适配 pea 后端）。 */
export default function Ecom() {
  return <EcommerceGallery />;
}
