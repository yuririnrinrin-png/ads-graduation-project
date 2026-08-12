import path from "path";
import sharp from "sharp";
import {
  CANVAS_SIZE,
  DEFAULT_TRANSFORM,
  getAnchors,
  type Category,
  type SlotTransform,
} from "@ti-amo/shared";

export { isBodySlot } from "@ti-amo/shared";

const SIZE = CANVAS_SIZE;

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
  /** One transform per anchor (2 for earrings = independent left/right). */
  transforms?: SlotTransform[];
  /** Optional detail image for wide_inset corner. */
  insetPath?: string;
}): Promise<void> {
  const anchors = getAnchors(opts.category, opts.body);

  let cutoutSharp = sharp(opts.cutoutPath).ensureAlpha();
  const mod = METAL_MODULATION[opts.metal];
  if (mod) {
    cutoutSharp = cutoutSharp.modulate(mod);
  }
  const baseCutoutBuf = await cutoutSharp.png().toBuffer();

  const composites: sharp.OverlayOptions[] = [];

  // Two anchors (earrings) = same jewel mirrored onto both ears; each anchor
  // keeps its own transform so left/right can be sized/placed independently.
  for (let i = 0; i < anchors.length; i++) {
    const anchor = anchors[i];
    const t = opts.transforms?.[i] ?? DEFAULT_TRANSFORM;
    const jewelW = Math.max(24, Math.round(SIZE * anchor.scale * t.scale));
    let jewelPipeline = sharp(baseCutoutBuf).resize(jewelW, jewelW, { fit: "inside" });
    if (i % 2 === 1) {
      jewelPipeline = jewelPipeline.flop();
    }
    const jewelBuf = await jewelPipeline.png().toBuffer();
    const meta = await sharp(jewelBuf).metadata();
    const jw = meta.width ?? jewelW;
    const jh = meta.height ?? jewelW;
    const cx = Math.round(SIZE * anchor.x + t.offsetX);
    const cy = Math.round(SIZE * anchor.y + t.offsetY);
    composites.push({
      input: jewelBuf,
      left: Math.max(0, cx - Math.floor(jw / 2)),
      top: Math.max(0, cy - Math.floor(jh / 2)),
    });
  }

  const base = sharp(opts.scenePath).resize(SIZE, SIZE).ensureAlpha();

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

export function previewPath(jobRoot: string, filename: string) {
  return path.join(jobRoot, "preview", filename);
}
