import fs from "fs/promises";
import path from "path";
import sharp from "sharp";
import {
  ALLOWED_UPLOAD_MIME,
  DATA_ROOT,
  MAX_UPLOAD_BYTES,
} from "@/lib/queue";

export type ImageKind = "personas" | "backgrounds";

const NAME_MAX = 40;

export function presetsRoot() {
  return path.join(DATA_ROOT, "presets");
}

export function parsePresetName(raw: unknown): string {
  const name = String(raw ?? "").trim();
  if (!name) {
    throw new Error("名前を入力してください");
  }
  if (name.length > NAME_MAX) {
    throw new Error(`名前は${NAME_MAX}文字以内です`);
  }
  return name;
}

export async function savePresetImage(
  kind: ImageKind,
  id: string,
  file: File
): Promise<string> {
  if (!ALLOWED_UPLOAD_MIME.has(file.type)) {
    throw new Error("対応形式は JPEG / PNG / WebP です");
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error("1枚あたり最大 12MB です");
  }
  const dir = path.join(presetsRoot(), kind);
  await fs.mkdir(dir, { recursive: true });
  const outPath = path.join(dir, `${id}.jpg`);
  const buf = Buffer.from(await file.arrayBuffer());
  const size = kind === "backgrounds" ? 2000 : 1200;
  await sharp(buf)
    .rotate()
    .resize(size, size, {
      fit: kind === "backgrounds" ? "cover" : "inside",
      withoutEnlargement: false,
    })
    .jpeg({ quality: 92 })
    .toFile(outPath);
  return outPath;
}

export async function removePresetImage(imageKey: string | null | undefined) {
  const full = resolvePresetFile(imageKey);
  if (!full) return;
  await fs.rm(full, { force: true });
}

/** Absolute path under DATA_ROOT/presets, or null if missing / unsafe / remote URL. */
export function resolvePresetFile(imageKey: string | null | undefined): string | null {
  const key = (imageKey ?? "").trim();
  if (!key || key.startsWith("http://") || key.startsWith("https://")) {
    return null;
  }
  const full = path.resolve(key);
  const root = path.resolve(DATA_ROOT);
  const rel = path.relative(root, full);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    return null;
  }
  return full;
}

export function publicPreset(
  row: { id: string; name: string; imageKey?: string | null },
  kind: ImageKind
) {
  const hasImage = Boolean(row.imageKey);
  return {
    id: row.id,
    name: row.name,
    hasImage,
    imageUrl: hasImage ? `/api/presets/${kind}/${row.id}/image` : null,
  };
}
