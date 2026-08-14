import fs from "fs/promises";
import path from "path";
import Redis from "ioredis";

const DATA_ROOT = process.env.DATA_ROOT
  ? path.resolve(process.env.DATA_ROOT)
  : path.join(process.cwd(), ".data");

export const QUEUE_KEY = "tiamo:jobs";

export function jobDir(jobId: string) {
  return path.join(DATA_ROOT, "jobs", jobId);
}

export function inputDir(jobId: string) {
  return path.join(jobDir(jobId), "input");
}

export async function ensureInputDir(jobId: string) {
  const dir = inputDir(jobId);
  await fs.mkdir(dir, { recursive: true });
  return dir;
}

/** Allowed upload types (DESIGN upload validation). */
export const ALLOWED_UPLOAD_MIME = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
]);

export const MAX_UPLOAD_BYTES = 12 * 1024 * 1024; // 12MB per file

let redis: Redis | null = null;

export function getRedis() {
  if (!redis) {
    redis = new Redis(process.env.REDIS_URL ?? "redis://localhost:6379", {
      maxRetriesPerRequest: 2,
    });
  }
  return redis;
}

export type QueuePayload = {
  jobId: string;
  /** Resume pipeline from this stage (inclusive). */
  fromStage?: string;
  /** If set, only regenerate these slots instead of the full pipeline. */
  slots?: string[];
};

export async function enqueueJob(
  jobId: string,
  extra?: Omit<QueuePayload, "jobId">
) {
  const r = getRedis();
  const hasExtra = Boolean(extra?.fromStage || extra?.slots?.length);
  const payload = hasExtra ? JSON.stringify({ jobId, ...extra }) : jobId;
  await r.lpush(QUEUE_KEY, payload);
}
