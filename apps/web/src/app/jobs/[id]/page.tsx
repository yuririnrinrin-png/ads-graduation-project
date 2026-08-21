import Link from "next/link";
import { notFound } from "next/navigation";
import {
  CATEGORY_LABELS,
  COMPOSITE_SLOTS,
  DEFAULT_TRANSFORM,
  DETAIL_SLOTS,
  getAnchors,
  isBodySlot,
  JOB_STATUS_LABELS,
  SLOT_KEYS,
  type Category,
  type DetailSlot,
  type JobStatus,
  type SlotKey,
  type SlotTransform,
} from "@ti-amo/shared";
import { DeleteJobButton } from "@/components/DeleteJobButton";
import { JobStatusPoller } from "@/components/JobStatusPoller";
import { ProgressPanel } from "@/components/ProgressPanel";
import { SlotCardClient } from "@/components/SlotCardClient";
import { prisma } from "@/lib/prisma";
import { purgeExpiredJobs } from "@/lib/purge-expired";
import { requirePageSession } from "@/lib/require-page-session";
import { remainingDays, retentionLabel } from "@/lib/retention";

type Props = { params: Promise<{ id: string }> };

function asTransform(value: unknown): SlotTransform {
  if (!value || typeof value !== "object") return DEFAULT_TRANSFORM;
  const v = value as Record<string, unknown>;
  return {
    scale: typeof v.scale === "number" ? v.scale : 1,
    offsetX: typeof v.offsetX === "number" ? v.offsetX : 0,
    offsetY: typeof v.offsetY === "number" ? v.offsetY : 0,
    rotate: typeof v.rotate === "number" ? v.rotate : 0,
    hidden: v.hidden === true,
  };
}

/** One transform per anchor (2 for earrings). Accepts legacy single-object
 * values too, applying the same transform to every anchor. */
function asTransformArray(value: unknown, count: number): SlotTransform[] {
  if (Array.isArray(value)) {
    return Array.from({ length: count }, (_, i) => asTransform(value[i]));
  }
  const single = asTransform(value);
  return Array.from({ length: count }, () => single);
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
    insetSlot?: string;
    updatedAt: Date;
    createdAt: Date;
    expiresAt: Date | null;
  };
  transforms: Partial<Record<SlotKey, SlotTransform[]>>;
}) {
  const imageVersion = job.updatedAt.getTime();
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
          <p
            className={remainingDays(job.createdAt, job.expiresAt) <= 3 ? "retention-warn" : "faint"}
            style={{ fontSize: "0.75rem", margin: "0.25rem 0 0" }}
          >
            ジョブ {job.id.slice(0, 8)} · 同一人物 {job.persona.name} · 2000×2000
            {" · "}
            {retentionLabel(job.createdAt, job.expiresAt)}
            {remainingDays(job.createdAt, job.expiresAt) <= 3
              ? " · 期限前に ZIP を保存してください"
              : ""}
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
            · ダメな枠は再生成。着用系はドラッグで大きさ・位置、スライダーで回転
          </span>
        </p>

        <div className="review-group">
          <h3 className="review-group-title">Detail · AI人物なし · 01–03</h3>
          <div className="slot-grid-3">
            {details.map((slot) => (
              <SlotCardClient key={slot} jobId={job.id} slot={slot} imageVersion={imageVersion} />
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
                initialTransforms={transforms[slot]}
                category={job.category as Category}
                body={false}
                imageVersion={imageVersion}
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
                initialTransforms={transforms[slot]}
                category={job.category as Category}
                body
                imageVersion={imageVersion}
                insetSlot={
                  (DETAIL_SLOTS as readonly string[]).includes(job.insetSlot ?? "")
                    ? (job.insetSlot as DetailSlot)
                    : "detail_a"
                }
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ExpiredView() {
  return (
    <div className="frame anim-rise">
      <div className="frame-bar">
        <p className="brand" style={{ fontSize: "1.25rem", margin: 0 }}>
          期限切れ
        </p>
      </div>
      <div className="frame-body">
        <p className="muted" style={{ fontSize: "0.9rem", margin: 0 }}>
          生成結果は14日で削除されました。ZIP は出せません。一覧の削除でこの行も消せます。
        </p>
      </div>
    </div>
  );
}

export default async function JobDetailPage({ params }: Props) {
  await requirePageSession();
  const { id } = await params;
  await purgeExpiredJobs(id);
  const job = await prisma.job.findUnique({
    where: { id },
    include: { persona: true, background: true, assets: true },
  });
  if (!job) notFound();

  const statusLabel = JOB_STATUS_LABELS[job.status as JobStatus] ?? job.status;
  const transforms: Partial<Record<SlotKey, SlotTransform[]>> = {};
  for (const asset of job.assets) {
    if (asset.kind === "preview" && asset.slotKey) {
      const slotKey = asset.slotKey as SlotKey;
      const anchorCount = getAnchors(job.category as Category, isBodySlot(slotKey)).length;
      transforms[slotKey] = asTransformArray(asset.transform, anchorCount);
    }
  }

  const title =
    job.status === "ready"
      ? "レビュー"
      : job.status === "failed"
        ? "進捗 · 失敗"
        : job.status === "expired"
          ? "期限切れ"
          : "進捗";

  return (
    <section className="stack" style={{ gap: "1.25rem" }}>
      <JobStatusPoller jobId={job.id} initialStatus={job.status} />
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <p className="section-kicker">Job · {statusLabel}</p>
          <h1 className="section-title">{title}</h1>
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
      ) : job.status === "expired" ? (
        <ExpiredView />
      ) : (
        <ProgressPanel job={job} failed={job.status === "failed"} />
      )}
    </section>
  );
}
