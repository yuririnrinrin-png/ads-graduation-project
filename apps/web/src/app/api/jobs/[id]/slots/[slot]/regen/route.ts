import { NextResponse } from "next/server";
import { SLOT_KEYS, type PipelineStage, type SlotKey } from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { enqueueJob } from "@/lib/queue";
import { busyResponse, isJobBusy } from "@/lib/job-busy";
import { falBudgetDenied, queueNeedsFal } from "@/lib/job-cost-guard";

type Params = { params: Promise<{ id: string; slot: string }> };

function regenStage(slot: string): PipelineStage {
  if (slot.startsWith("detail_")) return "detail";
  if (slot === "wide_inset") return "scene";
  return "scene";
}

export async function POST(_req: Request, { params }: Params) {
  const { error } = await requireSession();
  if (error) return error;

  const { id, slot } = await params;
  if (!(SLOT_KEYS as readonly string[]).includes(slot)) {
    return NextResponse.json({ error: "不明な枠です" }, { status: 400 });
  }

  const job = await prisma.job.findUnique({ where: { id } });
  if (!job) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (job.status === "expired") {
    return NextResponse.json({ error: "生成結果は14日で削除されました" }, { status: 410 });
  }
  if (job.status !== "ready") {
    return NextResponse.json(
      { error: "完了したジョブの枠だけ再生成できます" },
      { status: 400 }
    );
  }
  if (isJobBusy(job.status)) {
    return NextResponse.json(busyResponse(), { status: 409 });
  }

  const stage = regenStage(slot);
  if (queueNeedsFal({ slots: [slot] })) {
    const denied = falBudgetDenied(job.apiSpendYen);
    if (denied) {
      return NextResponse.json({ error: denied }, { status: 400 });
    }
  }

  await prisma.job.update({
    where: { id },
    data: { status: "queued", stage, error: null },
  });
  await enqueueJob(id, { slots: [slot as SlotKey] });
  return NextResponse.json({ ok: true, slot, stage });
}
