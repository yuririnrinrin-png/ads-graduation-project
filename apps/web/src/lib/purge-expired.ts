import { JOB_RETENTION_DAYS } from "@ti-amo/shared";
import { removeJobDir } from "@/lib/dummy-assets";
import { prisma } from "@/lib/prisma";

const PURGE_MESSAGE = "生成結果は14日で削除されました";

/** Delete on-disk images for jobs past expiresAt. Job rows stay as status=expired. */
export async function purgeExpiredJobs(jobId?: string): Promise<number> {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - JOB_RETENTION_DAYS);

  const due = await prisma.job.findMany({
    where: {
      ...(jobId ? { id: jobId } : {}),
      status: { notIn: ["expired", "running"] },
      OR: [{ expiresAt: { lte: new Date() } }, { AND: [{ expiresAt: null }, { createdAt: { lte: cutoff } }] }],
    },
    select: { id: true },
  });

  for (const job of due) {
    await removeJobDir(job.id);
    await prisma.job.update({
      where: { id: job.id },
      data: { status: "expired", error: PURGE_MESSAGE },
    });
  }
  return due.length;
}
