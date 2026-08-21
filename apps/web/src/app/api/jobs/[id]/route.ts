import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { removeJobDir } from "@/lib/dummy-assets";
import { purgeExpiredJobs } from "@/lib/purge-expired";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { error } = await requireSession();
  if (error) return error;

  const { id } = await params;
  await purgeExpiredJobs(id);
  const job = await prisma.job.findUnique({
    where: { id },
    include: { persona: true, background: true, assets: true },
  });
  if (!job) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json({ job });
}

export async function DELETE(_req: Request, { params }: Params) {
  const { error } = await requireSession();
  if (error) return error;

  const { id } = await params;
  const existing = await prisma.job.findUnique({ where: { id } });
  if (!existing) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await prisma.job.delete({ where: { id } });
  await removeJobDir(id);
  return NextResponse.json({ ok: true });
}
