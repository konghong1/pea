// 电商套图模块 · API 适配层 (pea 后端)
//
// 适配策略：
//   - 模型选择 → pea GET /models/available?type=image (真实后端)
//   - 生成提交 → pea POST /generation/jobs (真实后端)
//   - 任务状态 → pea GET /generation/jobs/:jobId (真实后端)
//   - 项目/策划项/模板/案例/上传/AI帮写 → localStorage 兜底（pea 无 gallery 后端）
//
// 导出与原版 @/services/gallery.ts 完全一致的类型签名，组件零修改即可运行。

import { listAvailableModels, acceptGenerationJob, type AvailableModel } from '../../api/catalog';
import { api } from '../../api/client';
// 原图走 MinIO：上传用 POST /files/upload，投递模型前用签名 URL 换回真实可外链地址。
// 与画布节点 (PeaNode / NodeChatPrompt) 完全同一套基础设施，不再各写一套。
import { getPresignedUrl } from '../../api/files';
// 真实「策划类型 + 配置项」数据：由 ai-agent 后端 gallery_config.serialize_types/serialize_options 生成，
// 与 ai-agent GET /api/gallery/types 返回完全一致（19 种推荐类型 + 通用/市场/输出选项）。
import { GALLERY_TYPES, DEFAULT_OPTIONS } from './galleryConfigData';

// ───────────────────────────── 类型定义（与原版 gallery.ts 对齐） ─────────────────────────────

export interface GalleryPersonalField {
  label: string
  placeholder?: string
  options?: string[]
}

export interface GalleryType {
  id: string
  title: string
  desc: string
  fast?: boolean
  hasResolution?: boolean
  points?: number
  minutes?: number
  ratioOptions?: string[] | null
  personal: GalleryPersonalField[]
}

export interface GalleryOptions {
  common: Record<string, string[]>
  market: Record<string, string[]>
  output: Record<string, any>
  showcase_categories: string[]
}

export interface GalleryImage {
  id: number
  project_id: number
  filename: string
  /**
   * 页面展示 & 草稿持久化用的图片地址。
   * 正常路径下是一张 ≤180KB 的**缩略图** data URL —— 只负责"给人看"，不参与模型投递。
   * 仅当原图上传 MinIO 失败（降级路径）时，这里才退回承载一张 ≤1.1MB 的内联图兜底。
   */
  url: string
  /**
   * 原图在 MinIO 的 object key（`POST /files/upload` 返回）。
   * 这是**发给模型的唯一真相源**：生成时用 getPresignedUrl(key) 换签名 URL，
   * 模型侧下载到的是未经前端压缩的原图。空串表示上传失败，已降级为 url 内联投递。
   */
  file_key?: string
  original: boolean
  order: number
  created_at: string
}

export interface GalleryPlanItem {
  id: number
  project_id: number
  type_id: string
  order: number
  personal_settings: Record<string, string>
  common_settings: Record<string, string>
  output_settings: Record<string, any>
  note: string
  reference_images: string[]
  product_image: string
  status: string
}

export interface GalleryProject {
  id: number
  user_id: number
  name: string
  status: string
  selling_points: string
  market_config: Record<string, string>
  output_config: Record<string, any>
  estimated_points: number
  estimated_minutes: number
  images: GalleryImage[]
  plan_items: GalleryPlanItem[]
  created_at: string
  updated_at: string
}

export interface GalleryRecord {
  id: number
  project_id: number
  plan_item_id: number | null
  type_id: string
  title: string
  result_filename: string | null
  result_url: string | null
  status: string
  error?: string | null
  prompt: string
  prompt_en: string | null
  prompt_source?: string
  prompt_input?: string | null
  prompt_raw?: string | null
  provider_id: number | null
  provider_name: string | null
  model_name: string | null
  created_at: string
  task_id?: number | null
  plan_item_snapshot?: {
    type_id: string
    personal_settings: Record<string, string>
    common_settings: Record<string, string>
    output_settings: Record<string, any>
    note: string
    reference_images: string[]
    product_image?: string
  } | null
}

export interface GalleryShowcase {
  id: number
  category: string
  name: string
  original_url: string
  image_urls: string[]
  total_count: number
  payload?: {
    plan_items?: Array<{
      type_id: string
      personal_settings?: Record<string, string>
      common_settings?: Record<string, string>
      output_settings?: Record<string, any>
      note?: string
      reference_images?: string[]
      product_image?: string
    }>
    market_config?: Record<string, string>
    output_config?: Record<string, any>
    selling_points?: string
  } | null
}

export interface GalleryTemplate {
  id: number
  user_id: number
  name: string
  payload: Record<string, any>
  cover_url: string | null
  created_at: string
}

export interface GalleryGenerateResponse {
  project_id: number
  status: string
  total_images: number
  total_points: number
  total_minutes: number
  records: GalleryRecord[]
}

export interface GalleryTask {
  id: number
  project_id: number
  name: string | null
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial'
  total: number
  done: number
  failed: number
  error: string | null
  created_at: string
  updated_at: string
  records: GalleryRecord[]
  /** 生成时使用的完整提示词（供提示词查看功能展示） */
  prompt?: string
}

export interface GalleryImageModelEntry {
  model_id: number
  model_name: string
  is_default: boolean
  allowed: boolean        // 用户是否有权使用
  minPlanLevel: number    // 所需权益等级
}

export interface GalleryImageModelProvider {
  provider_id: number
  provider_name: string
  is_default_provider: boolean
  models: GalleryImageModelEntry[]
}

export interface GalleryImageModelsResponse {
  providers: GalleryImageModelProvider[]
  default_image_model: {
    provider_id: number
    provider_name: string
    model_name: string
  } | null
}

export interface GalleryShowcaseCreate {
  name: string
  category: string
  record_ids: number[]
}

export interface AiSellingPoints {
  product_name: string
  selling_points: string
  audience: string
  scene: string
  params: string
}


// ───────────────────────────── localStorage 工具 ─────────────────────────────

const DRAFT_KEY = 'pea.gallery.draft'
const TASKS_KEY = 'pea.gallery.tasks'
const TEMPLATES_KEY = 'pea.gallery.templates'
const SHOWCASES_KEY = 'pea.gallery.showcases'
let _nextId = (() => {
  try { return parseInt(localStorage.getItem('pea.gallery.seq') || '1000', 10) }
  catch { return 1000 }
})()

function nextId(): number {
  const id = ++_nextId
  try { localStorage.setItem('pea.gallery.seq', String(id)) } catch {}
  return id
}

function nowUtc(): string {
  return new Date().toISOString().replace('Z', '')
}

// 离线 SVG 占位图（data URI，无需网络），用于无真实图的兜底
function placeholderImg(label: string): string {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'><rect width='100%' height='100%' fill='#F0EEE9'/><text x='50%' y='50%' font-family='sans-serif' font-size='15' fill='#908E98' text-anchor='middle' dominant-baseline='middle'>${label}</text></svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

function loadDraft(): GalleryProject | null {
  try { return JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null') } catch { return null }
}
/**
 * 持久化草稿。返回是否写入成功。
 *
 * ★ localStorage 每源配额仅约 5MB，而草稿里内联着 base64 产品图，极易打爆配额。
 * 旧实现 `catch {}` 静默吞掉 QuotaExceededError —— UI 显示"上传成功"，刷新后图全丢，
 * 用户零感知。这里改为返回布尔值 + 明确日志，由调用方决定是否回滚/提示。
 */
function saveDraft(p: GalleryProject): boolean {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(p))
    return true
  } catch (e) {
    console.error('[gallery] 草稿持久化失败（多半是超出 localStorage 配额）:', e)
    return false
  }
}

function loadTasks(): GalleryTask[] {
  try { return JSON.parse(localStorage.getItem(TASKS_KEY) || '[]') } catch { return [] }
}
function saveTasks(ts: GalleryTask[]): void {
  try { localStorage.setItem(TASKS_KEY, JSON.stringify(ts)) } catch {}
}

function loadTemplates(): GalleryTemplate[] {
  try { return JSON.parse(localStorage.getItem(TEMPLATES_KEY) || '[]') } catch { return [] }
}
function saveTemplates(t: GalleryTemplate[]): void {
  try { localStorage.setItem(TEMPLATES_KEY, JSON.stringify(t)) } catch {}
}

function loadShowcases(): GalleryShowcase[] {
  try { return JSON.parse(localStorage.getItem(SHOWCASES_KEY) || '[]') } catch { return [] }
}
function saveShowcases(s: GalleryShowcase[]): void {
  try { localStorage.setItem(SHOWCASES_KEY, JSON.stringify(s)) } catch {}
}

/** 确保草稿项目存在，不存在则创建空项目 */
function ensureDraft(): GalleryProject {
  let p = loadDraft()
  if (!p) {
    p = {
      id: 1, user_id: 0, name: '未命名套图', status: 'draft',
      selling_points: '', market_config: {}, output_config: {},
      estimated_points: 0, estimated_minutes: 0,
      images: [], plan_items: [],
      created_at: nowUtc(), updated_at: nowUtc(),
    }
    saveDraft(p)
  }
  return p
}

// ───────────────────────────── 配置 / 示例 ─────────────────────────────

export function getTypes(): Promise<{ types: GalleryType[]; options: GalleryOptions; features?: { show_prompt?: boolean } }> {
  return Promise.resolve({
    types: GALLERY_TYPES,
    options: DEFAULT_OPTIONS,
    features: { show_prompt: true },
  })
}

export function getShowcases(category?: string): Promise<GalleryShowcase[]> {
  let items = loadShowcases()
  if (category && category !== '全部') items = items.filter((s) => s.category === category)
  return Promise.resolve(items)
}

export function publishShowcase(data: GalleryShowcaseCreate): Promise<GalleryShowcase> {
  const sc: GalleryShowcase = {
    id: nextId(),
    category: data.category,
    name: data.name,
    original_url: '',
    image_urls: [],
    total_count: data.record_ids.length,
    payload: null,
  }
  const all = loadShowcases()
  all.unshift(sc)
  saveShowcases(all)
  return Promise.resolve(sc)
}

// ───────────────────────────── AI 提供商图片模型 → 适配 pea /models/available ─────────────────────────────

export async function getImageModels(): Promise<GalleryImageModelsResponse> {
  const models = await listAvailableModels('image')

  // 按 providerId 分组，显示所有模型但标记无权使用的（allowed=false）为禁用状态
  const providerMap = new Map<number, { provider_name: string; models: GalleryImageModelEntry[] }>()
  let defaultModel: GalleryImageModelsResponse['default_image_model'] = null

  for (const m of models) {
    // 只过滤掉禁用的模型，保留无权使用的模型（allowed=false）供前端置灰显示
    if (!m.enabled) continue
    const pid = Number(m.providerId)
    if (!providerMap.has(pid)) {
      providerMap.set(pid, { provider_name: m.displayName.split('/')[0]?.trim() || m.providerId, models: [] })
    }
    const entry: GalleryImageModelEntry = {
      model_id: Number(m.id.replace(/[^\d]/g, '')) || Math.floor(Math.random() * 100000),
      model_name: m.modelName,
      is_default: m.isDefault,
      allowed: m.allowed,        // 传递权限状态
      minPlanLevel: m.minPlanLevel,  // 传递所需权益等级
    }
    providerMap.get(pid)!.models.push(entry)
    // 默认模型：优先选择用户有权使用的 isDefault 模型
    if (m.isDefault && m.allowed && !defaultModel) {
      defaultModel = { provider_id: pid, provider_name: providerMap.get(pid)!.provider_name, model_name: m.modelName }
    }
  }

  // 如果没有从 isDefault 找到默认模型，取第一个有权使用的模型作为默认
  if (!defaultModel && models.length > 0) {
    const first = models.find((m) => m.enabled && m.allowed)
    if (first) {
      const pid = Number(first.providerId)
      defaultModel = {
        provider_id: pid,
        provider_name: first.displayName.split('/')[0]?.trim() || first.providerId,
        model_name: first.modelName,
      }
    }
  }

  const providers: GalleryImageModelProvider[] = Array.from(providerMap.entries()).map(([pid, data]) => ({
    provider_id: pid,
    provider_name: data.provider_name,
    is_default_provider: defaultModel?.provider_id === pid,
    models: data.models,
  }))

  return { providers, default_image_model: defaultModel }
}

// ───────────────────────────── 项目 ─────────────────────────────

export function getDraft(): Promise<GalleryProject> {
  return Promise.resolve(ensureDraft())
}

export function getProject(projectId: number): Promise<GalleryProject> {
  const p = loadDraft()
  return Promise.resolve(p?.id === projectId ? p! : ensureDraft())
}

export function updateProject(projectId: number, data: Partial<Pick<GalleryProject, 'name' | 'selling_points' | 'market_config' | 'output_config' | 'status'>>): Promise<GalleryProject> {
  const p = ensureDraft()
  Object.assign(p, data, { updated_at: nowUtc() })
  saveDraft(p)
  return Promise.resolve(p)
}

// ───────────────────────────── 产品图 ─────────────────────────────

// ═══════════════ 原图投递策略（2026-08-05 重构，与画布节点对齐） ═══════════════
//
// 旧实现：用户选的图先被 canvas 重编码压到 ~1.1MB，以 base64 内联进草稿存 localStorage，
//         再拿这张**残血图**当参考图。两个后果：
//           ① 高清原图在前端就被销毁 —— 8MB 的产品图，模型只看得到 1.1MB 的版本；
//           ② 草稿内联大图，localStorage 每源 ~5MB 配额永远悬在头顶（放不下 5 张）。
//
// 新实现：把「给人看的」和「给模型看的」彻底拆成两条通道 ——
//   ① 原图  → POST /files/upload（BFF 代理直写 MinIO，multipart 上限 100MB）→ 只留 object key。
//             生成时用 getPresignedUrl(key) 换真实签名 URL 投递，模型下载到的是**未经前端压缩的原图**。
//   ② 缩略图 → canvas 压到 ≤180KB / 长边 640，仅供页面预览与草稿持久化。
//             草稿里不再内联大图，5MB 配额从此不是瓶颈。
//
// ★ 「多大才需要压缩」的决策统一收敛到服务端，前端一律不替模型做画质取舍：
//   - param_adapters.RefImageBudget：≤10MB 原样透传（零解码零损失），>10MB 才逐张降采样；
//   - agnes_provider：上游若仍回 413 / "图片过大"，压缩后自愈重试一次。
//   前端这层只剩一个纯可用性闸门（MAX_PICK_BYTES），且直接对齐后端 multipart 上限。

/** 允许选择的单文件上限：与 BFF `POST /files/upload` 的 100MB multipart 限制对齐（超出必然 413，提前拦下给明确提示）。 */
export const MAX_PICK_BYTES = 100 * 1024 * 1024

/**
 * 预览缩略图的字节预算（按 data URL 字符串长度算）。
 * 只用于 UI 展示与草稿持久化，**永不作为模型输入**（除非原图上传失败走降级路径）。
 * 180KB × 十余张仍远低于 localStorage ~5MB 配额。
 */
const THUMB_BUDGET_BYTES = 180 * 1024

/** 预览缩略图最长边像素。画廊网格最大展示尺寸 ~200px，640 足够 2x 高清屏。 */
const THUMB_MAX_EDGE = 640

/**
 * 降级路径（原图上传 MinIO 失败）下的内联图预算。
 * 此时缩略图会成为唯一送模型的输入，180KB 太糊，退回旧的 1.1MB 档位保底画质。
 */
const FALLBACK_INLINE_BUDGET_BYTES = 1100 * 1024

/** 降级路径下的内联图最长边。 */
const FALLBACK_MAX_EDGE = 1600

/** 单次生成最多携带的参考图数量，防止请求体与上游计费失控。 */
const MAX_REFS_PER_JOB = 8

/** 探测 canvas 是否支持编码指定 MIME（用于判断 WebP 可用性）。 */
function canEncode(type: string): boolean {
  try {
    const c = document.createElement('canvas')
    c.width = 1
    c.height = 1
    return c.toDataURL(type).startsWith(`data:${type}`)
  } catch { return false }
}
let _webpOk: boolean | null = null
function webpSupported(): boolean {
  if (_webpOk === null) _webpOk = canEncode('image/webp')
  return _webpOk
}

/**
 * 把 File 用 canvas 压成 ≤ budget 字节的 data URL（仅用于**本地展示/兜底**，绝不代表原图）。
 *
 * - 本身已在预算内 → 原样读取，保留原始画质与透明通道；
 * - 超预算 → 逐轮降采样 + 降质量，直到进预算（最多 7 轮）。
 *   输出优先 WebP（同质量下比 JPEG 小 25~35%，且保留 alpha），浏览器不支持时回退 JPEG；
 *   回退 JPEG 时先铺白底，避免透明区域被渲染成黑块。
 */
function encodeToDataUrl(f: File, budget: number, maxEdge: number): Promise<string> {
  if (f.size <= budget) {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = () => resolve(placeholderImg(f.name))
      reader.readAsDataURL(f)
    })
  }
  return new Promise((resolve) => {
    const objUrl = URL.createObjectURL(f)
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(objUrl)
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) { resolve(placeholderImg(f.name)); return }
      const mime = webpSupported() ? 'image/webp' : 'image/jpeg'
      const keepAlpha = mime === 'image/webp' && /^image\/(png|webp|gif|avif)$/i.test(f.type)
      let scale = Math.min(maxEdge / Math.max(img.naturalWidth, img.naturalHeight), 1)
      let quality = 0.86
      let out = ''
      for (let round = 0; round < 7; round++) {
        canvas.width = Math.max(1, Math.round(img.naturalWidth * scale))
        canvas.height = Math.max(1, Math.round(img.naturalHeight * scale))
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        if (!keepAlpha) {
          ctx.fillStyle = '#FFFFFF'
          ctx.fillRect(0, 0, canvas.width, canvas.height)
        }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        out = canvas.toDataURL(mime, quality)
        if (out.length <= budget) break
        scale *= 0.8
        if (quality > 0.6) quality -= 0.08
      }
      resolve(out || placeholderImg(f.name))
    }
    img.onerror = () => { URL.revokeObjectURL(objUrl); resolve(placeholderImg(f.name)) }
    img.src = objUrl
  })
}

/** 生成预览缩略图（≤180KB / 长边 640）。 */
const makeThumb = (f: File) => encodeToDataUrl(f, THUMB_BUDGET_BYTES, THUMB_MAX_EDGE)

/**
 * 原图直传 MinIO（经 BFF multipart 代理，服务端落对象存储）。
 * 返回 object key；抛错交由调用方降级处理。与 PeaNode.onPickFile 同一条链路。
 */
async function putOriginalToStorage(f: File): Promise<string> {
  const form = new FormData()
  form.append('file', f)
  const { data } = await api.post<{ key: string }>('/files/upload', form)
  return data?.key || ''
}

export async function uploadImages(projectId: number, files: File[]): Promise<GalleryProject[]> {
  const p = ensureDraft()
  if (files.length === 0) return [p]

  const oversized = files.filter((f) => f.size > MAX_PICK_BYTES)
  if (oversized.length > 0) {
    const names = oversized.map((f) => f.name).join('、')
    throw new Error(
      `以下图片超过 ${Math.round(MAX_PICK_BYTES / 1024 / 1024)}MB 上传上限：${names}`,
    )
  }

  const startId = nextId()
  const baseCount = p.images.length

  // 用 Promise.all 保序：旧实现按"解码完成先后"入列，导致 order / original（首图）
  // 在多图并发上传时不确定 —— 谁先解码完谁就成了主图。这里改为严格按选择顺序。
  //
  // 每张图两件事并行：上传原图拿 key（给模型）+ 生成缩略图（给人看）。
  // 上传失败 fail-open：退回一张 ≤1.1MB 内联图兜底，功能可用性优先于画质，
  // 且在控制台留痕，避免"静默降质"这种最难查的问题。
  const prepared = await Promise.all(files.map(async (f) => {
    const [key, thumb] = await Promise.all([
      putOriginalToStorage(f).catch((e) => {
        console.warn('[gallery] 原图上传对象存储失败，降级为内联兜底图:', f.name, e)
        return ''
      }),
      makeThumb(f),
    ])
    if (key) return { key, url: thumb }
    const fallback = await encodeToDataUrl(f, FALLBACK_INLINE_BUDGET_BYTES, FALLBACK_MAX_EDGE)
    return { key: '', url: fallback }
  }))

  const newImages: GalleryImage[] = prepared.map((it, i) => ({
    id: startId + i,
    project_id: projectId,
    filename: files[i].name,
    url: it.url,
    file_key: it.key || undefined,
    original: baseCount === 0 && i === 0,
    order: baseCount + i,
    created_at: nowUtc(),
  }))
  p.images = [...p.images, ...newImages]
  p.updated_at = nowUtc()
  if (!saveDraft(p)) {
    // 回滚内存态，避免"UI 显示成功、刷新即丢"的假成功。
    p.images = p.images.slice(0, baseCount)
    throw new Error('浏览器本地存储空间不足，图片未保存。请先删除部分已上传的产品图后重试。')
  }
  return [p]
}

export function deleteImage(projectId: number, imageId: number): Promise<null> {
  const p = ensureDraft()
  p.images = p.images.filter((img) => img.id !== imageId)
  // 如果删的是原图，则将第一张设为原图
  if (p.images.length > 0 && !p.images.some((img) => img.original)) p.images[0].original = true
  p.updated_at = nowUtc()
  saveDraft(p)
  return Promise.resolve(null)
}

// ───────────────────────────── 策划项 ─────────────────────────────

export function createPlanItem(
  projectId: number,
  data: { type_id: string; personal_settings?: Record<string, string>; common_settings?: Record<string, string>; output_settings?: Record<string, any>; note?: string; reference_images?: string[]; product_image?: string },
): Promise<GalleryPlanItem> {
  const p = ensureDraft()
  const item: GalleryPlanItem = {
    id: nextId(),
    project_id: projectId,
    type_id: data.type_id,
    order: p.plan_items.length,
    personal_settings: data.personal_settings ?? {},
    common_settings: data.common_settings ?? {},
    output_settings: data.output_settings ?? {},
    note: data.note ?? '',
    reference_images: data.reference_images ?? [],
    product_image: data.product_image ?? p.images[0]?.url ?? '',
    status: 'pending',
  }
  p.plan_items = [...p.plan_items, item]
  p.updated_at = nowUtc()
  // 更新预估
  p.estimated_points = p.plan_items.reduce((s, it) => {
    const t = GALLERY_TYPES.find((x) => x.id === it.type_id)
    return s + (t?.points ?? 1) * (it.output_settings?.count || 1)
  }, 0)
  p.estimated_minutes = p.plan_items.reduce((s, it) => {
    const t = GALLERY_TYPES.find((x) => x.id === it.type_id)
    return s + (t?.minutes ?? 0.5) * (it.output_settings?.count || 1)
  }, 0)
  saveDraft(p)
  return Promise.resolve(item)
}

export function updatePlanItem(
  projectId: number,
  itemId: number,
  data: Partial<{ type_id: string; personal_settings: Record<string, string>; common_settings: Record<string, string>; output_settings: Record<string, any>; note: string; reference_images: string[]; product_image: string; order: number }>,
): Promise<GalleryPlanItem> {
  const p = ensureDraft()
  const idx = p.plan_items.findIndex((it) => it.id === itemId)
  if (idx < 0) throw new Error(`PlanItem ${itemId} not found`)
  p.plan_items[idx] = { ...p.plan_items[idx], ...data }
  p.updated_at = nowUtc()
  saveDraft(p)
  return Promise.resolve(p.plan_items[idx])
}

export function uploadPlanItemImage(projectId: number, file: File): Promise<{ filename: string; url: string }> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve({ filename: file.name, url: reader.result as string })
    reader.onerror = () => resolve({ filename: file.name, url: placeholderImg(file.name) })
    reader.readAsDataURL(file)
  })
}

export function deletePlanItem(projectId: number, itemId: number): Promise<null> {
  const p = ensureDraft()
  p.plan_items = p.plan_items.filter((it) => it.id !== itemId)
  p.updated_at = nowUtc()
  saveDraft(p)
  return Promise.resolve(null)
}

export function reorderPlanItems(projectId: number, orderedIds: number[]): Promise<GalleryProject> {
  const p = ensureDraft()
  const map = new Map(p.plan_items.map((it) => [it.id, it]))
  p.plan_items = orderedIds.map((id, i) => {
    const it = map.get(id)
    if (it) it.order = i
    return it!
  }).filter(Boolean)
  p.updated_at = nowUtc()
  saveDraft(p)
  return Promise.resolve(p)
}

// ───────────────────────────── AI 帮写（本地模拟兜底） ─────────────────────────────

export async function aiFill(
  _projectId: number,
  typeId: string,
  current: { personal_settings?: Record<string, string>; common_settings?: Record<string, string>; note?: string },
): Promise<{ common_settings: Record<string, string>; personal_settings: Record<string, string>; note: string }> {
  // 模拟 AI 填充延迟
  await new Promise((r) => setTimeout(r, 600))
  const typeDef = GALLERY_TYPES.find((t) => t.id === typeId)
  const suggestions: Record<string, string> = {}
  // 根据类型给一些智能默认建议
  if (typeDef) {
    for (const field of typeDef.personal) {
      if (!current.personal_settings?.[field.label] && field.options?.length) {
        suggestions[field.label] = field.options[Math.floor(Math.random() * field.options.length)]
      }
    }
  }
  return {
    personal_settings: { ...current.personal_settings, ...suggestions },
    common_settings: { ...(current.common_settings ?? {}) },
    note: current.note ?? '',
  }
}

export async function aiWriteSellingPoints(_projectId: number): Promise<AiSellingPoints> {
  await new Promise((r) => setTimeout(r, 800))
  return {
    product_name: '产品名称',
    selling_points: '核心卖点 1、核心卖点 2、核心卖点 3',
    audience: '目标受众描述',
    scene: '使用场景描述',
    params: '规格参数',
  }
}

// ───────────────────────────── 生成（→ pea 真实后端） ─────────────────────────────

/** pea jobId → local taskId 映射 */
const jobTaskMap = new Map<string, number>()

/**
 * 把「页面上展示用的图片地址」翻译成「可以真正发给模型的地址」。
 *
 * 草稿里 plan_item.reference_images / product_image 存的是展示用 URL（缩略图 data URL），
 * 直接发给模型等于把残血图当参考图。这里以 project.images 为登记表，
 * 展示 URL → file_key → getPresignedUrl 换成 MinIO 签名地址（指向**原图**）。
 *
 * 三级兜底，任何一环失败都不阻断生成：
 *   ① 有 file_key 且签名成功 → 用签名 URL（最佳：原图 + 按原始字节计量，无 base64 膨胀）
 *   ② 签名失败 / 无 key，但本身是 http(s) 或 data URL → 原样投递（兼容老草稿与降级图）
 *   ③ 其余（如 blob:、占位 SVG）→ 丢弃，模型侧下载不到只会徒增失败
 */
async function resolveSendableRefs(p: GalleryProject, displayUrls: string[]): Promise<string[]> {
  const keyByUrl = new Map<string, string>()
  for (const img of p.images) {
    if (img.file_key) keyByUrl.set(img.url, img.file_key)
  }

  const out: string[] = []
  const seenSource = new Set<string>()
  const seenResult = new Set<string>()
  for (const u of displayUrls) {
    if (out.length >= MAX_REFS_PER_JOB) break
    if (!u || seenSource.has(u)) continue
    seenSource.add(u)

    let sendable = ''
    const key = keyByUrl.get(u)
    if (key) {
      sendable = await getPresignedUrl(key)
      if (!sendable) console.warn('[gallery] 签名 URL 获取失败，回退内联投递:', key)
    }
    if (!sendable && (u.startsWith('http') || u.startsWith('data:image/'))) sendable = u
    if (!sendable || seenResult.has(sendable)) continue

    seenResult.add(sendable)
    out.push(sendable)
  }
  return out
}

/** 收集本次生成要携带的参考图（产品原图优先，其次各策划项自带参考图）。 */
async function collectJobRefs(p: GalleryProject): Promise<string[]> {
  const display: string[] = []
  // 产品原图放最前：images[0] 是主体，模型对靠前的参考图权重更高。
  for (const img of p.images) display.push(img.url)
  for (const it of p.plan_items) {
    if (it.product_image) display.push(it.product_image)
    for (const r of it.reference_images || []) display.push(r)
  }
  return resolveSendableRefs(p, display)
}

export async function generate(projectId: number): Promise<GalleryTask> {
  const p = ensureDraft()

  // 组装生成提示词
  const prompts: string[] = []
  for (const item of p.plan_items) {
    const typeDef = GALLERY_TYPES.find((t) => t.id === item.type_id)
    const settings = Object.entries(item.personal_settings).filter(([, v]) => v).map(([k, v]) => `${k}：${v}`).join('，')
    const common = Object.entries(item.common_settings).filter(([, v]) => v).map(([k, v]) => `${k}：${v}`).join('，')
    const cn = `${typeDef?.title || item.type_id}电商图。${p.selling_points ? '卖点：' + p.selling_points + '。' : ''}${settings ? '设置：' + settings + '。' : ''}${common ? '配置：' + common + '。' : ''}${item.note ? '备注：' + item.note : ''}`
    prompts.push(cn)
  }

  const masterPrompt = prompts.length === 1 ? prompts[0] : `[批量生成 ${prompts.length} 张]\n` + prompts.join('\n---\n')

  // 取用户选择的模型：
  // 优先从 plan_item.output_settings.model_name 读取（策划项级别），
  // 若无则回退到 project.output_config.model_name（项目级别，UI 实际写入位置）。
  const modelItem = p.plan_items.find((it) => it.output_settings?.model_name)
  let modelId = modelItem?.output_settings?.model_name || null
  if (!modelId) {
    modelId = p.output_config?.model_name || null
  }

  // 图片数：按各策划项 count 累加（用于计费倍率 + 提供商张数）
  const totalCount = p.plan_items.reduce((s, it) => s + (it.output_settings?.count || 1), 0)

  // 参考图：产品原图 + 各策划项自带参考图，翻译成模型可下载的签名 URL。
  // ★ 旧实现只发 prompt，用户上传的产品图从未抵达模型 —— "电商套图"实际退化成纯文生图，
  //   这也是后端逐张 10MB 压缩护栏一直没被触发的根因（到后端时根本没有图）。
  const referenceImages = await collectJobRefs(p)

  try {
    const result = await acceptGenerationJob({
      type: 'image',
      prompt: masterPrompt,
      model: modelId || undefined,
      params: {
        width: 1024,
        height: 1024,
        count: totalCount,
        // 计费倍率键名由模型 pricing.multiplier 约定为 'n'（见 PricingService.computeCost），
        // 必须显式传 n 才能按图片数扣减，否则只会扣 base。
        n: totalCount,
        // 编排器统一从 params.reference_images 取参考图（见 param_adapters.NormalizedParams）。
        // 空数组会被后端视为"有参考图但取不到"，故仅在非空时下发。
        ...(referenceImages.length ? { reference_images: referenceImages } : {}),
      },
    })

    // 创建本地任务对象
    const task: GalleryTask = {
      id: nextId(),
      project_id: projectId,
      name: p.name !== '未命名套图' ? p.name : null,
      status: 'pending',
      total: p.plan_items.reduce((s, it) => s + (it.output_settings?.count || 1), 0),
      done: 0,
      failed: 0,
      error: null,
      created_at: nowUtc(),
      updated_at: nowUtc(),
      records: [],
      prompt: masterPrompt, // 保存提示词供记录展示
    }

    // 映射 jobId 用于后续轮询
    jobTaskMap.set(result.jobId, task.id)

    // 保存任务到本地
    const tasks = loadTasks()
    tasks.unshift(task)
    saveTasks(tasks)

    // 启动轮询
    pollPeaJob(result.jobId, task.id)

    return task
  } catch (e: any) {
    console.error('[gallery-adapter] generate failed:', e)
    // 即使后端失败也返回一个本地 failed 任务，让 UI 能展示错误
    const task: GalleryTask = {
      id: nextId(),
      project_id: projectId,
      name: p.name !== '未命名套图' ? p.name : null,
      status: 'failed',
      total: 0,
      done: 0,
      failed: 0,
      error: e?.message || '生成任务提交失败',
      created_at: nowUtc(),
      updated_at: nowUtc(),
      records: [],
    }
    const tasks = loadTasks()
    tasks.unshift(task)
    saveTasks(tasks)
    return task
  }
}

/** 轮询 pea 后端任务状态并更新本地任务 */
async function pollPeaJob(jobId: string, localTaskId: number) {
  const maxAttempts = 120 // 最多轮询 5 分钟
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 2500))
    try {
      const { data } = await api.get<any>(`/generation/jobs/${jobId}`)
      const st = data.status
      const tasks = loadTasks()
      const ti = tasks.findIndex((t) => t.id === localTaskId)
      if (ti < 0) break // 任务已被删除

      if (st === 'completed' || st === 'done') {
        const resultUrl = data.resultUrl || data.result_url || null
        // 构建成功记录：优先用任务保存的完整提示词，回退到后端返回值
        const record: GalleryRecord = {
          id: nextId(),
          project_id: tasks[ti].project_id,
          plan_item_id: null,
          type_id: 'main',
          title: `成图 #${tasks[ti].done + 1}`,
          result_filename: resultUrl ? resultUrl.split('/').pop() : null,
          result_url: resultUrl,
          status: 'completed',
          error: null,
          prompt: tasks[ti].prompt || data.prompt || '',
          prompt_en: null,
          prompt_source: 'ai',
          provider_id: null,
          provider_name: null,
          model_name: data.model_name || null,
          created_at: nowUtc(),
          task_id: localTaskId,
          plan_item_snapshot: null,
        }
        tasks[ti].status = 'completed'
        tasks[ti].done = 1
        tasks[ti].total = 1
        tasks[ti].records = [record]
        tasks[ti].updated_at = nowUtc()
        saveTasks(tasks)
        break
      } else if (st === 'failed') {
        tasks[ti].status = 'failed'
        tasks[ti].error = data.error || '生成失败'
        tasks[ti].updated_at = nowUtc()
        saveTasks(tasks)
        break
      } else {
        // still running / queued
        tasks[ti].status = st === 'running' ? 'running' : 'pending'
        tasks[ti].updated_at = nowUtc()
        saveTasks(tasks)
      }
    } catch (e) {
      console.warn('[gallery-adapter] poll error:', e)
      // 网络错误不中断，继续轮询
    }
  }
}

// ───────────────────────────── 创作结果：任务查询 ─────────────────────────────

export function getTasks(): Promise<GalleryTask[]> {
  return Promise.resolve(loadTasks())
}

export function getTask(taskId: number): Promise<GalleryTask> {
  const tasks = loadTasks()
  const t = tasks.find((t) => t.id === taskId)
  return Promise.resolve(t || tasks[0])
}

export function deleteTask(taskId: number): Promise<null> {
  const tasks = loadTasks().filter((t) => t.id !== taskId)
  saveTasks(tasks)
  return Promise.resolve(null)
}

export function updateTask(taskId: number, data: { name?: string }): Promise<GalleryTask> {
  const tasks = loadTasks()
  const ti = tasks.findIndex((t) => t.id === taskId)
  if (ti >= 0) {
    Object.assign(tasks[ti], data)
    saveTasks(tasks)
    return Promise.resolve(tasks[ti])
  }
  throw new Error(`Task ${taskId} not found`)
}

export function updateRecord(recordId: number, data: { title?: string }): Promise<GalleryRecord> {
  const tasks = loadTasks()
  for (const t of tasks) {
    const ri = t.records?.find((r) => r.id === recordId)
    if (ri) {
      Object.assign(ri, data)
      saveTasks(tasks)
      return Promise.resolve(ri)
    }
  }
  throw new Error(`Record ${recordId} not found`)
}

export async function regenerateRecord(recordId: number, prompt?: string): Promise<GalleryRecord> {
  // 找到原始记录
  const tasks = loadTasks()
  let targetRec: GalleryRecord | null = null
  let targetTask: GalleryTask | null = null
  for (const t of tasks) {
    const r = t.records?.find((rec) => rec.id === recordId)
    if (r) { targetRec = r; targetTask = t; break }
  }
  if (!targetRec || !targetTask) throw new Error(`Record ${recordId} not found`)

  // 更新为 processing
  targetRec.status = 'processing'
  targetRec.result_url = null
  targetRec.error = null
  if (prompt) targetRec.prompt = prompt
  saveTasks(tasks)

  // 重新提交到 pea 后端。带上与首次生成同一套参考图，否则"重作"会退化成纯文生图，
  // 产出与原图主体对不上（用户视角就是"重作出来变了个产品"）。
  const refs = await collectJobRefs(ensureDraft())
  try {
    const result = await acceptGenerationJob({
      type: 'image',
      prompt: targetRec.prompt,
      params: {
        width: 1024, height: 1024, count: 1, n: 1,
        ...(refs.length ? { reference_images: refs } : {}),
      },
    })

    // 异步轮询
    pollPeaJobForRecord(result.jobId, targetTask.id, recordId)

    return targetRec
  } catch (e: any) {
    targetRec.status = 'failed'
    targetRec.error = e?.message || '重作提交失败'
    saveTasks(tasks)
    throw e
  }
}

async function pollPeaJobForRecord(jobId: string, taskId: number, recordId: number) {
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 2500))
    try {
      const { data } = await api.get<any>(`/generation/jobs/${jobId}`)
      const tasks = loadTasks()
      const t = tasks.find((tk) => tk.id === taskId)
      if (!t) break
      const rec = t.records?.find((r) => r.id === recordId)
      if (!rec) break

      if (data.status === 'completed' || data.status === 'done') {
        rec.status = 'completed'
        rec.result_url = data.resultUrl || data.result_url || null
        rec.result_filename = rec.result_url ? (rec.result_url.split('/').pop() || null) : null
        saveTasks(tasks)
        break
      } else if (data.status === 'failed') {
        rec.status = 'failed'
        rec.error = data.error || '重作失败'
        saveTasks(tasks)
        break
      }
    } catch { /* continue polling */ }
  }
}

export function getProjectRecords(_projectId: number): Promise<GalleryRecord[]> {
  const tasks = loadTasks()
  const records: GalleryRecord[] = []
  for (const t of tasks) {
    if (t.records) records.push(...t.records)
  }
  return Promise.resolve(records)
}

export function getMyRecords(): Promise<GalleryRecord[]> {
  return getProjectRecords(1)
}

// ───────────────────────────── 模板 ─────────────────────────────

export function createTemplate(name: string, payload: Record<string, any>, coverUrl?: string | null): Promise<GalleryTemplate> {
  const tpl: GalleryTemplate = {
    id: nextId(),
    user_id: 0,
    name,
    payload,
    cover_url: coverUrl || null,
    created_at: nowUtc(),
  }
  const all = loadTemplates()
  all.unshift(tpl)
  saveTemplates(all)
  return Promise.resolve(tpl)
}

export function getTemplates(): Promise<GalleryTemplate[]> {
  return Promise.resolve(loadTemplates())
}

export function updateTemplate(templateId: number, data: { name?: string; coverUrl?: string | null }): Promise<GalleryTemplate> {
  const all = loadTemplates()
  const ti = all.findIndex((t) => t.id === templateId)
  if (ti < 0) throw new Error(`Template ${templateId} not found`)
  if (data.name !== undefined) all[ti].name = data.name
  if (data.coverUrl !== undefined) all[ti].cover_url = data.coverUrl
  saveTemplates(all)
  return Promise.resolve(all[ti])
}

export function deleteTemplate(templateId: number): Promise<null> {
  saveTemplates(loadTemplates().filter((t) => t.id !== templateId))
  return Promise.resolve(null)
}

export function applyTemplate(templateId: number, projectId: number): Promise<GalleryProject> {
  const templates = loadTemplates()
  const tpl = templates.find((t) => t.id === templateId)
  if (!tpl) throw new Error(`Template ${templateId} not found`)

  const p = ensureDraft()
  const planItems = (tpl.payload?.plan_items || []).map((pi: any) => ({
    id: nextId(),
    project_id: projectId,
    type_id: pi.type_id || 'custom',
    order: p.plan_items.length,
    personal_settings: pi.personal_settings || {},
    common_settings: pi.common_settings || {},
    output_settings: pi.output_settings || {},
    note: pi.note || '',
    reference_images: pi.reference_images || [],
    product_image: pi.product_image || p.images[0]?.url || '',
    status: 'pending',
  }))
  p.plan_items = [...p.plan_items, ...planItems]
  if (tpl.payload?.selling_points) p.selling_points = tpl.payload.selling_points
  if (tpl.payload?.market_config) p.market_config = { ...p.market_config, ...tpl.payload.market_config }
  if (tpl.payload?.output_config) p.output_config = { ...p.output_config, ...tpl.payload.output_config }
  p.updated_at = nowUtc()
  saveDraft(p)
  return Promise.resolve(p)
}

// ───────────────────────────── Auth token（兼容原版 getToken） ─────────────────────────────

export function getToken(): string {
  try { return localStorage.getItem('pea_token') || '' } catch { return '' }
}
