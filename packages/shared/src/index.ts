/** Shared slot / filename / category contracts (Phase 1). */

export const CATEGORIES = [
  "necklace",
  "earring",
  "ring",
  "bracelet",
] as const;

export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_LABELS: Record<Category, string> = {
  necklace: "ネックレス",
  earring: "ピアス",
  ring: "リング",
  bracelet: "ブレスレット",
};

/** Wear-scene body-part hint shown on the new-job screen. */
export const CATEGORY_WEAR_HINTS: Record<Category, string> = {
  necklace: "着用シーンでは胸元〜顔（バストアップ）を写します",
  earring: "着用シーンでは顔まわりを写します",
  ring: "着用シーンでは手元を写します",
  bracelet: "着用シーンでは腕まわりを写します",
};

export const METALS = ["YG", "WG", "PG"] as const;
export type Metal = (typeof METALS)[number];

export const WEAR_SCENES = ["office", "cafe", "date", "holiday"] as const;
export type WearScene = (typeof WEAR_SCENES)[number];

export const SLOT_KEYS = [
  "detail_a",
  "detail_b",
  "detail_c",
  "wear_office",
  "wear_cafe",
  "wear_date",
  "wear_holiday",
  "body_1",
  "body_2",
  "wide_inset",
] as const;

export type SlotKey = (typeof SLOT_KEYS)[number];

/** ZIP entry names (REQUIREMENTS §6). */
export const ZIP_FILENAMES: Record<SlotKey, string> = {
  detail_a: "01_detail_a.jpg",
  detail_b: "02_detail_b.jpg",
  detail_c: "03_detail_c.jpg",
  wear_office: "04_wear_office.jpg",
  wear_cafe: "05_wear_cafe.jpg",
  wear_date: "06_wear_date.jpg",
  wear_holiday: "07_wear_holiday.jpg",
  body_1: "08_body_tone1.jpg",
  body_2: "09_body_tone2.jpg",
  wide_inset: "10_wide_inset.jpg",
};

/** Short UI labels for review grid. */
export const SLOT_LABELS: Record<SlotKey, string> = {
  detail_a: "ディテール A",
  detail_b: "ディテール B",
  detail_c: "ディテール C",
  wear_office: "オフィス",
  wear_cafe: "カフェ",
  wear_date: "デート",
  wear_holiday: "休日",
  body_1: "全身トーン1",
  body_2: "全身トーン2",
  wide_inset: "引き + インセット",
};

/** Badge text on thumbnails (mock style). */
export const SLOT_BADGES: Record<SlotKey, string> = {
  detail_a: "01 detail_a",
  detail_b: "02 detail_b",
  detail_c: "03 detail_c",
  wear_office: "04 office",
  wear_cafe: "05 cafe",
  wear_date: "06 date",
  wear_holiday: "07 holiday",
  body_1: "08 body · トーン1",
  body_2: "09 body · トーン2",
  wide_inset: "10 wide_inset",
};

/** User-facing progress steps (DESIGN §3 / mock Screen 03). */
export const PROGRESS_STEPS = [
  { key: "cutout", label: "切り抜き" },
  { key: "detail", label: "ディテール（背景・色調整）" },
  { key: "scene", label: "人物シーン生成" },
  { key: "composite", label: "実物合成" },
  { key: "inset", label: "仕上げ（インセット）" },
] as const;

export const PIPELINE_STAGES = [
  "ingest",
  "cutout",
  "detail",
  "scene",
  "composite",
  "inset",
  "ready",
] as const;

export type PipelineStage = (typeof PIPELINE_STAGES)[number];

export const PIPELINE_STAGE_LABELS: Record<PipelineStage, string> = {
  ingest: "取り込み",
  cutout: "切り抜き",
  detail: "ディテール",
  scene: "人物シーン",
  composite: "合成",
  inset: "仕上げ",
  ready: "完了",
};

export const JOB_STATUSES = [
  "queued",
  "running",
  "ready",
  "failed",
  "expired",
] as const;

export type JobStatus = (typeof JOB_STATUSES)[number];

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  queued: "待機",
  running: "生成中",
  ready: "完了",
  failed: "失敗",
  expired: "期限切れ",
};

/** v1 soft assumption: few concurrent jobs. */
export const V1_CONCURRENT_JOBS_HINT = 2;

/** Progress polling interval (ms). */
export const PROGRESS_POLL_MS = 4000;

/** Jewelry placement on person scenes (fractions of 2000×2000 + relative scale). */
export type SlotTransform = {
  scale: number;
  offsetX: number;
  offsetY: number;
};

export const DEFAULT_TRANSFORM: SlotTransform = {
  scale: 1,
  offsetX: 0,
  offsetY: 0,
};

/**
 * Max |offsetX/Y| in canvas pixels. Face-based auto placement on a tight
 * bust crop can need ~700px of shift from CATEGORY_ANCHORS; keep headroom
 * so the user can still drag after that. Must match
 * apps/worker/worker/face_anchor.py OFFSET_LIMIT.
 */
export const TRANSFORM_OFFSET_LIMIT = 1000;

/**
 * `rotate` (degrees, clockwise) is an optional fixed baseline tilt applied at
 * composite time — NOT a per-shot 3D perspective correction, and not
 * user-adjustable via drag (REQUIREMENTS.md §5/§8 still rule out real
 * perspective auto-correction / AI-drawn jewelry). It only exists to break
 * up the perfectly flat/"pasted on" look of a straight cutout sitting on a
 * neck/ear that is rarely perfectly upright. Defaults to 0 when omitted.
 */
export type Anchor = { x: number; y: number; scale: number; rotate?: number };

/**
 * Anchor points = center of jewelry on canvas (0–1), scale = width vs canvas.
 * Categories with 2 anchors (earring) get the single uploaded/cutout jewel
 * mirrored onto the second anchor — no need to shoot left/right separately
 * (REQUIREMENTS.md §2 決定 2026-08-12).
 */
export const CATEGORY_ANCHORS: Record<Category, Anchor[]> = {
  necklace: [{ x: 0.5, y: 0.36, scale: 0.28, rotate: 6 }],
  earring: [
    { x: 0.4, y: 0.32, scale: 0.09, rotate: 6 },
    { x: 0.6, y: 0.32, scale: 0.09, rotate: -6 },
  ],
  ring: [{ x: 0.58, y: 0.66, scale: 0.13 }],
  bracelet: [{ x: 0.46, y: 0.55, scale: 0.2 }],
};

/** Full-body frames use a slightly lower / smaller default. */
export const BODY_ANCHORS: Record<Category, Anchor[]> = {
  necklace: [{ x: 0.5, y: 0.32, scale: 0.14, rotate: 4 }],
  earring: [
    { x: 0.46, y: 0.22, scale: 0.045, rotate: 4 },
    { x: 0.54, y: 0.22, scale: 0.045, rotate: -4 },
  ],
  ring: [{ x: 0.55, y: 0.58, scale: 0.07 }],
  bracelet: [{ x: 0.48, y: 0.48, scale: 0.1 }],
};

export const WEAR_SLOTS = [
  "wear_office",
  "wear_cafe",
  "wear_date",
  "wear_holiday",
] as const;

export const COMPOSITE_SLOTS = [
  ...WEAR_SLOTS,
  "body_1",
  "body_2",
  "wide_inset",
] as const;

export function isBodySlot(slot: string): boolean {
  return slot === "body_1" || slot === "body_2" || slot === "wide_inset";
}

/** Anchor points for a category/frame combo (2 for earrings = left/right ear). */
export function getAnchors(category: Category, body: boolean): Anchor[] {
  const table = body ? BODY_ANCHORS : CATEGORY_ANCHORS;
  return table[category] ?? CATEGORY_ANCHORS.bracelet;
}

export function defaultTransforms(count: number): SlotTransform[] {
  return Array.from({ length: count }, () => ({ ...DEFAULT_TRANSFORM }));
}

/** Logical square canvas size (px) all composited/scene images are rendered at. */
export const CANVAS_SIZE = 2000;
