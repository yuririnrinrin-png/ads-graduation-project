import fs from "fs/promises";
import path from "path";
import sharp from "sharp";
import archiver from "archiver";
import { PassThrough } from "stream";
import { SLOT_KEYS, ZIP_FILENAMES, type SlotKey } from "@ti-amo/shared";
import { jobDir } from "@/lib/queue";

export { jobDir } from "@/lib/queue";

/** Remove on-disk job folder (preview JPEGs etc.). Missing dir is OK. */
export async function removeJobDir(jobId: string) {
  await fs.rm(jobDir(jobId), { recursive: true, force: true });
}

/** Placeholder JPEGs for slots not yet produced by the worker (Phase 2: wear/body still dummy). */
export async function writeDummySlotImages(
  jobId: string,
  onlySlots?: SlotKey[]
): Promise<Record<string, string>> {
  const dir = path.join(jobDir(jobId), "preview");
  await fs.mkdir(dir, { recursive: true });

  const colors: Record<SlotKey, { r: number; g: number; b: number }> = {
    detail_a: { r: 232, g: 220, b: 200 },
    detail_b: { r: 220, g: 210, b: 190 },
    detail_c: { r: 210, g: 200, b: 180 },
    wear_office: { r: 180, g: 170, b: 160 },
    wear_cafe: { r: 170, g: 150, b: 130 },
    wear_date: { r: 160, g: 140, b: 150 },
    wear_holiday: { r: 150, g: 165, b: 140 },
    body_1: { r: 140, g: 130, b: 120 },
    body_2: { r: 130, g: 120, b: 110 },
    wide_inset: { r: 120, g: 110, b: 100 },
  };

  const slots = onlySlots ?? [...SLOT_KEYS];
  const keys: Record<string, string> = {};

  for (const slot of slots) {
    const file = path.join(dir, ZIP_FILENAMES[slot]);
    const { r, g, b } = colors[slot];
    const svg = `
      <svg width="2000" height="2000" xmlns="http://www.w3.org/2000/svg">
        <rect width="2000" height="2000" fill="rgb(${r},${g},${b})"/>
        <text x="1000" y="980" text-anchor="middle" font-size="72" font-family="Arial, sans-serif" fill="#1A1612">${slot}</text>
        <text x="1000" y="1080" text-anchor="middle" font-size="40" font-family="Arial, sans-serif" fill="#5C534A">placeholder</text>
      </svg>`;
    await sharp(Buffer.from(svg)).jpeg({ quality: 85 }).toFile(file);
    keys[slot] = file;
  }

  return keys;
}

export async function buildZipBuffer(jobId: string): Promise<Buffer> {
  const dir = path.join(jobDir(jobId), "preview");
  const archive = archiver("zip", { zlib: { level: 9 } });
  const pass = new PassThrough();
  const chunks: Buffer[] = [];

  pass.on("data", (chunk: Buffer) => chunks.push(chunk));

  const done = new Promise<Buffer>((resolve, reject) => {
    pass.on("end", () => resolve(Buffer.concat(chunks)));
    archive.on("error", reject);
  });

  archive.pipe(pass);

  for (const slot of SLOT_KEYS) {
    const name = ZIP_FILENAMES[slot];
    archive.file(path.join(dir, name), { name });
  }

  await archive.finalize();
  return done;
}
