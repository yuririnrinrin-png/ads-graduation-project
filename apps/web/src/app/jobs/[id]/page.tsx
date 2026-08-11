import Link from "next/link";
import { notFound } from "next/navigation";
import {
  CATEGORY_LABELS,
  COMPOSITE_SLOTS,
  DEFAULT_TRANSFORM,
  JOB_STATUS_LABELS,
  PIPELINE_STAGE_LABELS,
  PROGRESS_STEPS,
  SLOT_KEYS,
  type Category,
  type JobStatus,
  type PipelineStage,
  type SlotKey,
  type SlotTransform,
} from "@ti-amo/shared";
import { DeleteJobButton } from "@/components/DeleteJobButton";
import { JobStatusPoller } from "@/components/JobStatusPoller";
import { SlotCardClient } from "@/components/SlotCardClient";
import { prisma } from "@/lib/prisma";
import { requirePageSession } from "@/lib/require-page-session";

type Props = { params: Promise<{ id: string }> };

function progressIndex(stage: string | null | undefined): number {
  if (!stage || stage === "ingest") return 0;
  if (stage === "ready") return PROGRESS_STEPS.length;
  const idx = PROGRESS_STEPS.findIndex((s) => s.key === stage);
  return idx >= 0 ? idx : 0;
}

function asTransform(value: unknown): SlotTransform {
  if (!value || typeof value !== "object") return DEFAULT_TRANSFORM;
  const v = value as Record<string, unknown>;
  return {
    scale: typeof v.scale === "number" ? v.scale : 1,
    offsetX: typeof v.offsetX === "number" ? v.offsetX : 0,
    offsetY: typeof v.offsetY === "number" ? v.offsetY : 0,
  };
}

function ReviewView({
  job,
  transforms,
}: {
  job: {
    id: string;
    persona: { name: string };
    background: { name: string };
    category: string;
    metal: string;
  };
  transforms: Partial<Record<SlotKey, SlotTransform>>;
}) {
  const details = SLOT_KEYS.slice(0, 3) as SlotKey[];
  const wears = SLOT_KEYS.slice(3, 7) as SlotKey[];
  const bodies = SLOT_KEYS.slice(7, 10) as SlotKey[];
  const adjustable = new Set<string>(COMPOSITE_SLOTS);

  return (
    <div className="frame anim-rise">
      <div className="frame-bar">
        <div>
          <p className="brand" style={{ fontSize: "1.25rem", margin: 0 }}>
            10枚の確認
          </p>
          <p className="faint" style={{ fontSize: "0.75rem", margin: "0.25rem 0 0" }}>
            ジョブ {job.id.slice(0, 8)} · 同一人物 {job.persona.name} · 2000×2000
          </p>
        </div>
        <a className="btn btn-primary" href={`/api/jobs/${job.id}/zip`}>
          ZIPをダウンロード
        </a>
      </div>

      <div className="frame-body">
        <p className="muted" style={{ fontSize: "0.8rem", margin: "0 0 1.5rem" }}>
          {CATEGORY_LABELS[job.category as Category] ?? job.category} · {job.metal} ·{" "}
          {job.persona.name} · {job.background.name}
          <span className="faint">
            {" "}
            · 着用系は大きさ・位置を調整可。人物シーンはローカル仮生成（本番APIは後続）
          </span>
        </p>

        <div className="review-group">
          <h3 className="review-group-title">Detail · AI人物なし · 01–03</h3>
          <div className="slot-grid-3">
            {details.map((slot) => (
              <SlotCardClient key={slot} jobId={job.id} slot={slot} />
            ))}
          </div>
        </div>

        <div className="review-group">
          <h3 className="review-group-title">Wear · 着用シーン · 04–07</h3>
          <div className="slot-grid-4">
            {wears.map((slot) => (
              <SlotCardClient
                key={slot}
                jobId={job.id}
                slot={slot}
                adjustable={adjustable.has(slot)}
                initialTransform={transforms[slot]}
              />
            ))}
          </div>
        </div>

        <div className="review-group">
          <h3 className="review-group-title">Body &amp; Inset · 08–10</h3>
          <div className="slot-grid-3">
            {bodies.map((slot) => (
              <SlotCardClient
                key={slot}
                jobId={job.id}
                slot={slot}
                adjustable={adjustable.has(slot)}
                initialTransform={transforms[slot]}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ProgressView({
  job,
  failed,
}: {
  job: {
    id: string;
    stage: string | null;
    error: string | null;
    category: string;
    metal: string;
    persona: { name: string };
    background: { name: string };
  };
  failed: boolean;
}) {
  const current = progressIndex(job.stage);
  const failAt = failed ? current : -1;
  const pct = failed
    ? Math.max(12, (current / PROGRESS_STEPS.length) * 100)
    : Math.min(95, ((current + 0.4) / PROGRESS_STEPS.length) * 100);
  const stageLabel =
    PIPELINE_STAGE_LABELS[job.stage as PipelineStage] ?? job.stage ?? "処理";

  return (
    <div className="frame anim-rise">
      <div className="progress-panel">
        {failed ? (
          <>
            <p className="fail-badge">FAILED</p>
            <h1
              className="hero-title"
              style={{ fontSize: "clamp(1.75rem, 4vw, 2.25rem)", marginTop: "1rem" }}
            >
              {stageLabel}で失敗しました
            </h1>
            <p className="muted" style={{ maxWidth: "28rem", margin: "0.5rem auto 0", fontSize: "0.875rem" }}>
              {job.error ?? `段階「${stageLabel}」でエラー。`}
            </p>
          </>
        ) : (
          <>
            <h1 className="hero-title" style={{ fontSize: "clamp(1.75rem, 4vw, 2.25rem)" }}>
              生成しています
            </h1>
            <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.875rem" }}>
              {CATEGORY_LABELS[job.category as Category] ?? job.category} · {job.metal} ·{" "}
              {job.persona.name} · {job.background.name}
            </p>
            <div className="progress-bar">
              <span style={{ width: `${pct}%` }} />
            </div>
            <p className="faint" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }}>
              全体の目安 2〜4分 · 数秒ごとに状態を更新します
            </p>
          </>
        )}

        <ol className="stage-list">
          {PROGRESS_STEPS.map((step, i) => {
            let cls = "stage-item";
            let mark: string | number = i + 1;
            if (failed && i === failAt) {
              cls += " failed";
              mark = "!";
            } else if (i < current || (!failed && job.stage === "ready")) {
              cls += " done";
              mark = "✓";
            } else if (!failed && i === current) {
              cls += " current";
              mark = String(i + 1);
            }
            return (
              <li key={step.key} className={cls}>
                <span className="stage-dot">{mark}</span>
                {step.label}
                {failed && i === failAt ? " — 失敗" : ""}
              </li>
            );
          })}
        </ol>

        {failed ? (
          <div className="row" style={{ marginTop: "2.5rem", justifyContent: "center" }}>
            <Link className="btn btn-ghost" href="/jobs/new">
              最初から（新規ジョブ）
            </Link>
            <span
              className="btn btn-primary"
              style={{ opacity: 0.55, cursor: "not-allowed" }}
              title="Phase 4"
            >
              失敗した段階からリトライ
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default async function JobDetailPage({ params }: Props) {
  await requirePageSession();
  const { id } = await params;
  const job = await prisma.job.findUnique({
    where: { id },
    include: { persona: true, background: true, assets: true },
  });
  if (!job) notFound();

  const statusLabel = JOB_STATUS_LABELS[job.status as JobStatus] ?? job.status;
  const transforms: Partial<Record<SlotKey, SlotTransform>> = {};
  for (const asset of job.assets) {
    if (asset.kind === "preview" && asset.slotKey) {
      transforms[asset.slotKey as SlotKey] = asTransform(asset.transform);
    }
  }

  return (
    <section className="stack" style={{ gap: "1.25rem" }}>
      <JobStatusPoller jobId={job.id} initialStatus={job.status} />
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <p className="section-kicker">Job · {statusLabel}</p>
          <h1 className="section-title">
            {job.status === "ready" ? "レビュー" : job.status === "failed" ? "進捗 · 失敗" : "進捗"}
          </h1>
        </div>
        <div className="row" style={{ gap: "0.5rem" }}>
          <DeleteJobButton jobId={job.id} redirectTo="/" />
          <Link className="btn btn-ghost" href="/">
            一覧へ
          </Link>
        </div>
      </div>

      {job.status === "ready" ? (
        <ReviewView job={job} transforms={transforms} />
      ) : (
        <ProgressView job={job} failed={job.status === "failed"} />
      )}
    </section>
  );
}
