import Link from "next/link";
import { CATEGORY_LABELS, type Category } from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requirePageSession } from "@/lib/require-page-session";

export default async function HomePage() {
  await requirePageSession();
  const jobs = await prisma.job.findMany({
    orderBy: { createdAt: "desc" },
    take: 20,
    include: { persona: true, background: true },
  });

  return (
    <section className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 className="hero-title">ジョブ</h1>
          <p className="muted">Phase 1: 認証・ジョブ CRUD・ダミー10枚 ZIP</p>
        </div>
        <Link className="btn btn-gold" href="/jobs/new">
          新規ジョブ
        </Link>
      </div>

      <div className="card">
        {jobs.length === 0 ? (
          <p className="muted">まだジョブがありません。新規ジョブからダミー10枚を作れます。</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>状態</th>
                <th>カテゴリ</th>
                <th>人物</th>
                <th>作成</th>
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
                    <span className="badge">{job.status}</span>
                  </td>
                  <td>{CATEGORY_LABELS[job.category as Category] ?? job.category}</td>
                  <td>{job.persona.name}</td>
                  <td className="muted">{job.createdAt.toLocaleString("ja-JP")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
