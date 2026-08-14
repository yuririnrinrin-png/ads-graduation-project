import { NextResponse } from "next/server";
import { z } from "zod";
import { DETAIL_SLOTS } from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { enqueueJob } from "@/lib/queue";
import { busyResponse, isJobBusy } from "@/lib/job-busy";

type Params = { params: Promise<{ id: string }> };

const bodySchema = z.object({
  insetSlot: z.enum(DETAIL_SLOTS),
});

export async function PATCH(req: Request, { params }: Params) {
  const { error } = await requireSession();
  if (error) return error;

  const { id } = await params;
  const json = await req.json().catch(() => null);
  const parsed = bodySchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json({ error: "ディテール A / B / C を選んでください" }, { status: 400 });
  }

  const job = await prisma.job.findUnique({ where: { id } });
  if (!job) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (job.status !== "ready") {
    return NextResponse.json({ error: "完了したジョブだけインセットを変えられます" }, { status: 400 });
  }
  if (isJobBusy(job.status)) {
    return NextResponse.json(busyResponse(), { status: 409 });
  }

  await prisma.job.update({
    where: { id },
    data: {
      insetSlot: parsed.data.insetSlot,
      status: "queued",
      stage: "inset",
      error: null,
    },
  });
  await enqueueJob(id, { fromStage: "inset" });
  return NextResponse.json({ ok: true, insetSlot: parsed.data.insetSlot });
}
