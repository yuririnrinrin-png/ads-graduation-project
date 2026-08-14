import path from "path";
import fs from "fs";
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

/** Must match apps/worker/worker/pipeline.py SCENE_SHADOW_* . */
const SCENE_SHADOW_BLUR = 12;
const SCENE_SHADOW_OPACITY = 48;

const METAL_MODULATION: Record<string, { brightness: number; saturation: number; hue: number }> = {
  YG: { brightness: 1.05, saturation: 1.15, hue: 15 },
  WG: { brightness: 1.02, saturation: 0.85, hue: 0 },
  PG: { brightness: 1.04, saturation: 1.1, hue: -20 },
};

/**
 * Soft blurred dark silhouette from an RGBA cutout's alpha channel, used as
 * a light contact shadow so a flat real-photo cutout doesn't read as
 * "pasted on top" of the scene — NOT a 3D relight, just a cheap grounding
 * cue (REQUIREMENTS.md §5: no AI-drawn jewelry, no real perspective
 * correction; this is a lightweight exception approved 2026-08-13, see
 * docs/HANDOFF.md). Must mirror apps/worker/worker/pipeline.py's
 * `make_shadow_layer`. Returns the shadow PNG buffer and `pad` (how much
 * bigger the shadow canvas is on each side vs. the input).
 */
async function makeShadowLayer(
  jewelBuf: Buffer,
  opts: { blur: number; opacity: number }
): Promise<{ buf: Buffer; pad: number }> {
  const pad = opts.blur * 2;
  const { data, info } = await sharp(jewelBuf)
    .ensureAlpha()
    .extractChannel(3)
    .linear(opts.opacity / 255, 0)
    .extend({
      top: pad,
      bottom: pad,
      left: pad,
      right: pad,
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    })
    .raw()
    .toBuffer({ resolveWithObject: true });

  const buf = await sharp({
    create: {
      width: info.width,
      height: info.height,
      channels: 3,
      background: { r: 40, g: 34, b: 28 },
    },
  })
    .joinChannel(data, {
      raw: { width: info.width, height: info.height, channels: 1 },
    })
    .blur(opts.blur)
    .png()
    .toBuffer();

  return { buf, pad };
}

async function matchJewelToScene(
  jewelBuf: Buffer,
  scenePath: string,
  cx: number,
  cy: number,
  jewelW: number,
  jewelH: number
): Promise<Buffer> {
  const radius = Math.max(24, Math.round(Math.max(jewelW, jewelH) / 3));
  const left = Math.max(0, cx - radius);
  const top = Math.max(0, cy - radius);
  const width = Math.min(SIZE - left, radius * 2);
  const height = Math.min(SIZE - top, radius * 2);
  if (width < 4 || height < 4) return jewelBuf;

  const patch = await sharp(scenePath)
    .extract({ left, top, width, height })
    .raw()
    .toBuffer({ resolveWithObject: true });
  const pc = patch.info.channels;
  let sR = 0;
  let sG = 0;
  let sB = 0;
  const pCount = patch.info.width * patch.info.height;
  for (let i = 0; i < patch.data.length; i += pc) {
    sR += patch.data[i];
    sG += patch.data[i + 1];
    sB += patch.data[i + 2];
  }
  sR /= pCount;
  sG /= pCount;
  sB /= pCount;
  const sY = 0.299 * sR + 0.587 * sG + 0.114 * sB;

  const jewel = await sharp(jewelBuf).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const { data, info } = jewel;
  let jR = 0;
  let jG = 0;
  let jB = 0;
  let n = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] <= 32) continue;
    jR += data[i];
    jG += data[i + 1];
    jB += data[i + 2];
    n += 1;
  }
  if (n < 50) return jewelBuf;
  jR /= n;
  jG /= n;
  jB /= n;
  const jY = 0.299 * jR + 0.587 * jG + 0.114 * jB;
  const scale = jY < 8 ? 1 : Math.min(1.06, Math.max(0.94, sY / jY));

  const out = Buffer.from(data);
  for (let i = 0; i < out.length; i += 4) {
    if (out[i + 3] <= 32) continue;
    out[i] = Math.max(0, Math.min(255, Math.round(out[i] * scale)));
    out[i + 1] = Math.max(0, Math.min(255, Math.round(out[i + 1] * scale)));
    out[i + 2] = Math.max(0, Math.min(255, Math.round(out[i + 2] * scale)));
  }

  return sharp(out, {
    raw: { width: info.width, height: info.height, channels: 4 },
  })
    .png()
    .toBuffer();
}

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
  /** Optional hair overlay (tucked-down slots) composited above jewelry. */
  hairOverlayPath?: string;
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
    // Fixed baseline tilt (not a 3D perspective fix, see Anchor docstring in
    // packages/shared/src/index.ts) so a straight cutout doesn't look
    // perfectly flat/pasted on a neck or ear that is rarely upright.
    const rotate = (anchor.rotate ?? 0) + (t.rotate ?? 0);
    if (rotate) {
      jewelPipeline = jewelPipeline.rotate(rotate, {
        background: { r: 0, g: 0, b: 0, alpha: 0 },
      });
    }
    const jewelBuf = await jewelPipeline.png().toBuffer();
    const matchedBuf = await matchJewelToScene(
      jewelBuf,
      opts.scenePath,
      Math.round(SIZE * anchor.x + t.offsetX),
      Math.round(SIZE * anchor.y + t.offsetY),
      jewelW,
      jewelW
    );
    const meta = await sharp(matchedBuf).metadata();
    const jw = meta.width ?? jewelW;
    const jh = meta.height ?? jewelW;
    const cx = Math.round(SIZE * anchor.x + t.offsetX);
    const cy = Math.round(SIZE * anchor.y + t.offsetY);
    const left = Math.max(0, cx - Math.floor(jw / 2));
    const top = Math.max(0, cy - Math.floor(jh / 2));

    // Matches apps/worker/worker/pipeline.py composite_on_scene exactly.
    const { buf: shadowBuf, pad } = await makeShadowLayer(matchedBuf, {
      blur: SCENE_SHADOW_BLUR,
      opacity: SCENE_SHADOW_OPACITY,
    });
    const shadowOffset = Math.max(5, Math.round(jw * 0.025));
    composites.push({
      input: shadowBuf,
      left: Math.max(0, left - pad),
      top: Math.max(0, top - pad + shadowOffset),
    });
    composites.push({
      input: matchedBuf,
      left,
      top,
    });
  }

  if (opts.hairOverlayPath && fs.existsSync(opts.hairOverlayPath)) {
    composites.push({
      input: opts.hairOverlayPath,
      left: 0,
      top: 0,
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
