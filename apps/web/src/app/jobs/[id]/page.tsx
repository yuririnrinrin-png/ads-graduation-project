import Link from "next/link";
import { CATEGORY_LABELS, PIPELINE_STAGE_LABELS, type Category, type PipelineStage } from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requirePageSession } from "@/lib/require-page-session";
import { notFound } from "next/navigation";

type Props = { params: Promise<{ id: string }> };

export default async function JobDetailPage({ params }: Props) {
  await requirePageSession();
  const { id } = await params;
  const job = await prisma.job.findUnique({
    where: { id },
    include: { persona: true, background: true, assets: true },
  });
  if (!job) notFound();

  return (
    <section className="stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 className="hero-title">ジョブ詳細</h1>
          <p className="muted">{job.id}</p>
        </div>
        <Link className="btn btn-ghost" href="/">
          一覧へ
        </Link>
      </div>

      <div className="card stack">
        <div className="row">
          <span className="badge">{job.status}</span>
          {job.stage ? (
            <span className="muted">
              段階: {PIPELINE_STAGE_LABELS[job.stage as PipelineStage] ?? job.stage}
            </span>
          ) : null}
        </div>
        <p>
          {CATEGORY_LABELS[job.category as Category] ?? job.category} · {job.metal} ·{" "}
          {job.persona.name} · {job.background.name}
        </p>
        {job.error ? <p className="error">失敗: {job.error}</p> : null}
        <p className="muted">プレビュー枠: {job.assets.filter((a) => a.kind === "preview").length} / 10</p>
        {job.status === "ready" ? (
          <a className="btn btn-gold" href={`/api/jobs/${job.id}/zip`}>
            ZIPをダウンロード
          </a>
        ) : (
          <p className="muted">ready になると ZIP を落とせます。</p>
        )}
      </div>
    </section>
  );
}
