import Link from "next/link";
import {
  CATEGORY_LABELS,
  JOB_STATUS_LABELS,
  type Category,
  type JobStatus,
} from "@ti-amo/shared";
import { DeleteJobButton } from "@/components/DeleteJobButton";
import { prisma } from "@/lib/prisma";
import { requirePageSession } from "@/lib/require-page-session";

function statusClass(status: string) {
  if (status === "ready") return "badge badge-ready";
  if (status === "failed") return "badge badge-failed";
  if (status === "running" || status === "queued") return "badge badge-running";
  return "badge";
}

export default async function HomePage() {
  await requirePageSession();
  const jobs = await prisma.job.findMany({
    orderBy: { createdAt: "desc" },
    include: { persona: true, background: true },
  });

  return (
    <div className="anim-rise">
      <div className="page-head">
        <div>
          <p className="section-kicker">Jobs</p>
          <h1 className="section-title">ジョブ</h1>
          <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.875rem" }}>
            3枚を上げる → 待つ → 直す → ZIP
          </p>
        </div>
        <div className="row" style={{ gap: "0.75rem", alignItems: "center" }}>
          <Link className="link" href="/presets">
            プリセット
          </Link>
          <Link className="btn btn-gold" href="/jobs/new">
            新規ジョブ
          </Link>
        </div>
      </div>

      <div className="frame">
        <div className="frame-bar">
          <p className="brand" style={{ fontSize: "1.25rem", margin: 0 }}>
            すべてのジョブ
          </p>
          <span className="faint" style={{ fontSize: "0.75rem" }}>
            {jobs.length} 件 · 新しい順
          </span>
        </div>
        <div className="frame-body" style={{ paddingTop: "0.5rem", paddingBottom: "0.5rem" }}>
          {jobs.length === 0 ? (
            <p className="muted" style={{ padding: "1rem 0" }}>
              まだジョブがありません。新規ジョブからダミー10枚を作れます。
            </p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>ジョブ</th>
                  <th>状態</th>
                  <th>カテゴリ</th>
                  <th>人物</th>
                  <th>作成</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td>
                      <Link className="link" href={`/jobs/${job.id}`}>
                        {job.id.slice(0, 8)}…
                      </Link>
                    </td>
                    <td>
                      <span className={statusClass(job.status)}>
                        {JOB_STATUS_LABELS[job.status as JobStatus] ?? job.status}
                      </span>
                    </td>
                    <td>{CATEGORY_LABELS[job.category as Category] ?? job.category}</td>
                    <td>{job.persona.name}</td>
                    <td className="faint">{job.createdAt.toLocaleString("ja-JP")}</td>
                    <td style={{ textAlign: "right" }}>
                      <DeleteJobButton jobId={job.id} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
