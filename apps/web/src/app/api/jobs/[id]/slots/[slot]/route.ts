import { NextResponse } from "next/server";
import { z } from "zod";
import path from "path";
import {
  COMPOSITE_SLOTS,
  DEFAULT_TRANSFORM,
  ZIP_FILENAMES,
  type Category,
  type SlotKey,
} from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { jobDir } from "@/lib/queue";
import { isBodySlot, recompositeSlot } from "@/lib/recomposite";

type Ctx = { params: Promise<{ id: string; slot: string }> };

const bodySchema = z.object({
  scale: z.number().min(0.3).max(2.5),
  offsetX: z.number().min(-600).max(600),
  offsetY: z.number().min(-600).max(600),
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
  const transform = parsed.data;

  const job = await prisma.job.findUnique({ where: { id } });
  if (!job || job.status !== "ready") {
    return NextResponse.json({ error: "Job not ready" }, { status: 400 });
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
  if (!scene || !cutout || !preview) {
    return NextResponse.json({ error: "Missing scene/cutout/preview" }, { status: 400 });
  }

  const outName = ZIP_FILENAMES[slot as SlotKey];
  const outPath = path.join(jobDir(id), "preview", outName);

  let insetPath: string | undefined;
  if (slot === "wide_inset") {
    const detail = await prisma.jobAsset.findFirst({
      where: { jobId: id, slotKey: "detail_a", kind: "preview" },
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
      body: isBodySlot(slot),
      transform,
      insetPath,
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Recomposite failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }

  const updated = await prisma.jobAsset.update({
    where: { id: preview.id },
    data: {
      storageKey: outPath,
      transform: transform ?? DEFAULT_TRANSFORM,
    },
  });

  return NextResponse.json({ ok: true, transform: updated.transform });
}
