import { NextResponse } from "next/server";
import { z } from "zod";
import { CATEGORIES, METALS } from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { writeDummySlotImages } from "@/lib/dummy-assets";

const createJobSchema = z.object({
  category: z.enum(CATEGORIES),
  metal: z.enum(METALS),
  mainIndex: z.number().int().min(0).max(2).default(0),
  personaId: z.string().min(1),
  backgroundId: z.string().min(1),
  toneIds: z.array(z.string()).length(2),
});

export async function GET() {
  const { error } = await requireSession();
  if (error) return error;

  const jobs = await prisma.job.findMany({
    orderBy: { createdAt: "desc" },
    take: 50,
    include: {
      persona: true,
      background: true,
    },
  });
  return NextResponse.json({ jobs });
}

export async function POST(req: Request) {
  const { error } = await requireSession();
  if (error) return error;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = createJobSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const data = parsed.data;
  const [persona, background, tones] = await Promise.all([
    prisma.presetPersona.findUnique({ where: { id: data.personaId } }),
    prisma.presetBackground.findUnique({ where: { id: data.backgroundId } }),
    prisma.presetTone.findMany({ where: { id: { in: data.toneIds } } }),
  ]);

  if (!persona || !background || tones.length !== 2) {
    return NextResponse.json({ error: "Unknown preset id(s)" }, { status: 400 });
  }

  const expiresAt = new Date();
  expiresAt.setDate(expiresAt.getDate() + 14);

  // Phase 1: create job and immediately fill with dummy 10 images (no real worker yet).
  const job = await prisma.job.create({
    data: {
      status: "running",
      stage: "ingest",
      category: data.category,
      metal: data.metal,
      mainIndex: data.mainIndex,
      personaId: data.personaId,
      backgroundId: data.backgroundId,
      toneIds: data.toneIds,
      expiresAt,
    },
  });

  try {
    const files = await writeDummySlotImages(job.id);
    await prisma.jobAsset.createMany({
      data: Object.entries(files).map(([slotKey, storageKey]) => ({
        jobId: job.id,
        slotKey,
        kind: "preview",
        storageKey,
      })),
    });
    const ready = await prisma.job.update({
      where: { id: job.id },
      data: { status: "ready", stage: "ready", error: null },
      include: { persona: true, background: true, assets: true },
    });
    return NextResponse.json({ job: ready }, { status: 201 });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Dummy generation failed";
    const failed = await prisma.job.update({
      where: { id: job.id },
      data: { status: "failed", stage: "detail", error: message },
    });
    return NextResponse.json({ job: failed, error: message }, { status: 500 });
  }
}
