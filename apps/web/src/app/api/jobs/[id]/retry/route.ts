import { NextResponse } from "next/server";
import { z } from "zod";
import { PIPELINE_STAGES, type PipelineStage } from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { enqueueJob } from "@/lib/queue";
import { busyResponse, isJobBusy, retryFromStage } from "@/lib/job-busy";
import { falBudgetDenied, queueNeedsFal } from "@/lib/job-cost-guard";

type Params = { params: Promise<{ id: string }> };

const bodySchema = z.object({
  mode: z.enum(["start", "failed"]),
  force: z.boolean().optional(),
});

export async function POST(req: Request, { params }: Params) {
  const { error } = await requireSession();
  if (error) return error;

  const { id } = await params;
  const json = await req.json().catch(() => null);
  const parsed = bodySchema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json({ error: "mode は start か failed です" }, { status: 400 });
  }

  const job = await prisma.job.findUnique({ where: { id } });
  if (!job) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (job.status === "expired") {
    return NextResponse.json({ error: "期限切れのジョブはリトライできません" }, { status: 410 });
  }
  if (isJobBusy(job.status) && !parsed.data.force) {
    return NextResponse.json(busyResponse(), { status: 409 });
  }
  if (parsed.data.mode === "failed" && job.status !== "failed" && !parsed.data.force) {
    return NextResponse.json({ error: "失敗したジョブだけ段階リトライできます" }, { status: 400 });
  }

  const fromStage =
    parsed.data.mode === "start" ? "ingest" : retryFromStage("failed", job.stage);
  const stage = (PIPELINE_STAGES as readonly string[]).includes(fromStage)
    ? (fromStage as PipelineStage)
    : "ingest";

  if (queueNeedsFal({ fromStage: stage })) {
    const denied = falBudgetDenied(job.apiSpendYen);
    if (denied) {
      return NextResponse.json({ error: denied }, { status: 400 });
    }
  }

  await prisma.job.update({
    where: { id },
    data: { status: "queued", stage, error: null },
  });
  await enqueueJob(id, { fromStage: stage });
  return NextResponse.json({ ok: true, fromStage: stage });
}
