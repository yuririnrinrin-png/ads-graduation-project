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

/** v1 soft assumption: few concurrent jobs. */
export const V1_CONCURRENT_JOBS_HINT = 2;

/** Progress polling interval (ms). */
export const PROGRESS_POLL_MS = 4000;
