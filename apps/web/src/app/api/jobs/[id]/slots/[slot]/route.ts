import { NextResponse } from "next/server";
import { z } from "zod";
import path from "path";
import {
  COMPOSITE_SLOTS,
  TRANSFORM_OFFSET_LIMIT,
  TRANSFORM_ROTATE_LIMIT,
  defaultTransforms,
  getAnchors,
  isBodySlot,
  ZIP_FILENAMES,
  type Category,
  type SlotKey,
} from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { jobDir } from "@/lib/queue";
import { recompositeSlot } from "@/lib/recomposite";

type Ctx = { params: Promise<{ id: string; slot: string }> };

const transformItemSchema = z.object({
  scale: z.number().min(0.3).max(2.5),
  offsetX: z.number().min(-TRANSFORM_OFFSET_LIMIT).max(TRANSFORM_OFFSET_LIMIT),
  offsetY: z.number().min(-TRANSFORM_OFFSET_LIMIT).max(TRANSFORM_OFFSET_LIMIT),
  rotate: z.number().min(-TRANSFORM_ROTATE_LIMIT).max(TRANSFORM_ROTATE_LIMIT).optional().default(0),
  hidden: z.boolean().optional().default(false),
});

const bodySchema = z.object({
  transforms: z.array(transformItemSchema).min(1).max(2),
});

export async function PATCH(req: Request, ctx: Ctx) {
  const { error } = await requireSession();
  if (error) return error;

  const { id, slot } = await ctx.params;
  if (!(COMPOSITE_SLOTS as readonly string[]).includes(slot)) {
    return NextResponse.json({ error: "Slot is not adjustable" }, { status: 400 });
  }

  let json: unknown;
  try {
    json = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const parsed = bodySchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json({ error: "Validation failed" }, { status: 400 });
  }

  const job = await prisma.job.findUnique({ where: { id } });
  if (!job || job.status !== "ready") {
    return NextResponse.json({ error: "Job not ready" }, { status: 400 });
  }

  const body = isBodySlot(slot);
  const anchors = getAnchors(job.category as Category, body);
  if (parsed.data.transforms.length !== anchors.length) {
    return NextResponse.json(
      { error: `Expected ${anchors.length} transform(s) for this slot` },
      { status: 400 }
    );
  }
  const transforms = parsed.data.transforms;
  if (
    job.category === "earring" &&
    transforms.length > 1 &&
    transforms.every((t) => t.hidden)
  ) {
    return NextResponse.json(
      { error: "Earrings cannot all be hidden" },
      { status: 400 }
    );
  }

  const scene = await prisma.jobAsset.findFirst({
    where: { jobId: id, slotKey: slot, kind: "scene" },
  });
  const cutout = await prisma.jobAsset.findFirst({
    where: { jobId: id, slotKey: `cutout_${job.mainIndex}`, kind: "cutout" },
  });
  const preview = await prisma.jobAsset.findFirst({
    where: { jobId: id, slotKey: slot, kind: "preview" },
  });
  const hairOverlay = await prisma.jobAsset.findFirst({
    where: { jobId: id, slotKey: slot, kind: "hair_overlay" },
  });
  if (!scene || !cutout || !preview) {
    return NextResponse.json({ error: "Missing scene/cutout/preview" }, { status: 400 });
  }

  const outName = ZIP_FILENAMES[slot as SlotKey];
  const outPath = path.join(jobDir(id), "preview", outName);

  let insetPath: string | undefined;
  if (slot === "wide_inset") {
    const insetKey = job.insetSlot || "detail_a";
    const detail = await prisma.jobAsset.findFirst({
      where: { jobId: id, slotKey: insetKey, kind: "preview" },
    });
    insetPath = detail?.storageKey;
  }

  try {
    await recompositeSlot({
      scenePath: scene.storageKey,
      cutoutPath: cutout.storageKey,
      outPath,
      category: job.category as Category,
      metal: job.metal,
      body,
      transforms,
      insetPath,
      hairOverlayPath:
        job.category === "necklace" ? hairOverlay?.storageKey : undefined,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Recomposite failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }

  const updated = await prisma.jobAsset.update({
    where: { id: preview.id },
    data: {
      storageKey: outPath,
      transform: transforms ?? defaultTransforms(anchors.length),
    },
  });

  return NextResponse.json({ ok: true, transforms: updated.transform });
}
