import { NextResponse } from "next/server";
import { z } from "zod";
import path from "path";
import sharp from "sharp";
import { CATEGORIES, DETAIL_SLOTS, METALS } from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import {
  ALLOWED_UPLOAD_MIME,
  MAX_UPLOAD_BYTES,
  ensureInputDir,
  enqueueJob,
} from "@/lib/queue";

const metaSchema = z.object({
  category: z.enum(CATEGORIES),
  metal: z.enum(METALS),
  mainIndex: z.coerce.number().int().min(0).max(2).default(0),
  personaId: z.string().min(1),
  backgroundId: z.string().min(1),
  toneIds: z.array(z.string()).length(2),
  insetSlot: z.enum(DETAIL_SLOTS).default("detail_a"),
});

export async function GET() {
  const { error } = await requireSession();
  if (error) return error;

  const jobs = await prisma.job.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      persona: true,
      background: true,
    },
  });
  return NextResponse.json({ jobs, total: jobs.length });
}

async function saveNormalizedInput(
  jobId: string,
  index: number,
  file: File
): Promise<string> {
  if (!ALLOWED_UPLOAD_MIME.has(file.type)) {
    throw new Error(`対応形式は JPEG / PNG / WebP です（${file.name}）`);
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error(`1枚あたり最大 12MB です（${file.name}）`);
  }

  const dir = await ensureInputDir(jobId);
  const outPath = path.join(dir, `product_${index + 1}.jpg`);
  const buf = Buffer.from(await file.arrayBuffer());
  await sharp(buf)
    .rotate()
    .resize(2000, 2000, { fit: "inside", withoutEnlargement: false })
    .jpeg({ quality: 92 })
    .toFile(outPath);
  return outPath;
}

export async function POST(req: Request) {
  const { error } = await requireSession();
  if (error) return error;

  const contentType = req.headers.get("content-type") ?? "";
  if (!contentType.includes("multipart/form-data")) {
    return NextResponse.json(
      { error: "multipart/form-data で商品写真3枚を送ってください" },
      { status: 400 }
    );
  }

  const form = await req.formData();
  const toneRaw = String(form.get("toneIds") ?? "");
  let toneIds: string[] = [];
  try {
    toneIds = JSON.parse(toneRaw);
  } catch {
    toneIds = toneRaw.split(",").map((s) => s.trim()).filter(Boolean);
  }

  const parsed = metaSchema.safeParse({
    category: form.get("category"),
    metal: form.get("metal"),
    mainIndex: form.get("mainIndex"),
    personaId: form.get("personaId"),
    backgroundId: form.get("backgroundId"),
    toneIds,
    insetSlot: form.get("insetSlot") || "detail_a",
  });

  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const files = [0, 1, 2].map((i) => form.get(`image${i}`));
  if (files.some((f) => !(f instanceof File) || f.size === 0)) {
    return NextResponse.json(
      { error: "商品写真は3枚すべて必要です" },
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

  const job = await prisma.job.create({
    data: {
      status: "queued",
      stage: "ingest",
      category: data.category,
      metal: data.metal,
      mainIndex: data.mainIndex,
      personaId: data.personaId,
      backgroundId: data.backgroundId,
      toneIds: data.toneIds,
      insetSlot: data.insetSlot,
      expiresAt,
    },
  });

  try {
    const paths: string[] = [];
    for (let i = 0; i < 3; i++) {
      const file = files[i] as File;
      const storageKey = await saveNormalizedInput(job.id, i, file);
      paths.push(storageKey);
      await prisma.jobAsset.create({
        data: {
          jobId: job.id,
          slotKey: `input_${i}`,
          kind: "input",
          storageKey,
        },
      });
    }

    await enqueueJob(job.id);

    const created = await prisma.job.findUnique({
      where: { id: job.id },
      include: { persona: true, background: true, assets: true },
    });
    return NextResponse.json({ job: created }, { status: 201 });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Job create failed";
    await prisma.job.update({
      where: { id: job.id },
      data: { status: "failed", stage: "ingest", error: message },
    });
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
