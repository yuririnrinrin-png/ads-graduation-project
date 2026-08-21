import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { buildZipBuffer } from "@/lib/dummy-assets";
import { purgeExpiredJobs } from "@/lib/purge-expired";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { error } = await requireSession();
  if (error) return error;

  const { id } = await params;
  await purgeExpiredJobs(id);
  const job = await prisma.job.findUnique({ where: { id } });
  if (!job) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (job.status === "expired") {
    return NextResponse.json({ error: "生成結果は14日で削除されました" }, { status: 410 });
  }
  if (job.status !== "ready") {
    return NextResponse.json({ error: "Job is not ready" }, { status: 409 });
  }

  const zip = await buildZipBuffer(id);
  return new NextResponse(new Uint8Array(zip), {
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": `attachment; filename="tiamo-${id}.zip"`,
    },
  });
}
