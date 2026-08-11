import path from "path";
import sharp from "sharp";
import {
  BODY_ANCHORS,
  CATEGORY_ANCHORS,
  DEFAULT_TRANSFORM,
  type Category,
  type SlotTransform,
} from "@ti-amo/shared";

const SIZE = 2000;

const METAL_MODULATION: Record<string, { brightness: number; saturation: number; hue: number }> = {
  YG: { brightness: 1.05, saturation: 1.15, hue: 15 },
  WG: { brightness: 1.02, saturation: 0.85, hue: 0 },
  PG: { brightness: 1.04, saturation: 1.1, hue: -20 },
};

export async function recompositeSlot(opts: {
  scenePath: string;
  cutoutPath: string;
  outPath: string;
  category: Category;
  metal: string;
  body: boolean;
  transform?: SlotTransform;
  /** Optional detail image for wide_inset corner. */
  insetPath?: string;
}): Promise<void> {
  const t = opts.transform ?? DEFAULT_TRANSFORM;
  const anchors = opts.body ? BODY_ANCHORS : CATEGORY_ANCHORS;
  const anchor = anchors[opts.category] ?? CATEGORY_ANCHORS.bracelet;
  const jewelW = Math.max(32, Math.round(SIZE * anchor.scale * t.scale));

  let cutout = sharp(opts.cutoutPath).ensureAlpha();
  const mod = METAL_MODULATION[opts.metal];
  if (mod) {
    cutout = cutout.modulate(mod);
  }
  const jewelBuf = await cutout
    .resize(jewelW, jewelW, { fit: "inside" })
    .png()
    .toBuffer();
  const jewelMeta = await sharp(jewelBuf).metadata();
  const jw = jewelMeta.width ?? jewelW;
  const jh = jewelMeta.height ?? jewelW;
  const cx = Math.round(SIZE * anchor.x + t.offsetX);
  const cy = Math.round(SIZE * anchor.y + t.offsetY);
  const left = cx - Math.floor(jw / 2);
  const top = cy - Math.floor(jh / 2);

  let base = sharp(opts.scenePath).resize(SIZE, SIZE).ensureAlpha();

  const composites: sharp.OverlayOptions[] = [
    { input: jewelBuf, left: Math.max(0, left), top: Math.max(0, top) },
  ];

  if (opts.insetPath) {
    const insetSize = 520;
    const thumb = await sharp(opts.insetPath)
      .resize(insetSize, insetSize, { fit: "inside" })
      .png()
      .toBuffer();
    const tm = await sharp(thumb).metadata();
    const tw = (tm.width ?? insetSize) + 16;
    const th = (tm.height ?? insetSize) + 16;
    const frame = await sharp({
      create: {
        width: tw,
        height: th,
        channels: 4,
        background: { r: 255, g: 255, b: 255, alpha: 0.9 },
      },
    })
      .composite([{ input: thumb, left: 8, top: 8 }])
      .png()
      .toBuffer();
    const pad = 48;
    composites.push({
      input: frame,
      left: SIZE - tw - pad,
      top: SIZE - th - pad,
    });
  }

  await base
    .composite(composites)
    .flatten({ background: "#ffffff" })
    .jpeg({ quality: 90 })
    .toFile(opts.outPath);
}

export function isBodySlot(slot: string) {
  return slot === "body_1" || slot === "body_2" || slot === "wide_inset";
}

export function previewPath(jobRoot: string, filename: string) {
  return path.join(jobRoot, "preview", filename);
}
