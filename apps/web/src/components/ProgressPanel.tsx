"use client";

import { useEffect, useState } from "react";
import {
  CATEGORY_LABELS,
  JOB_COST_YEN_LIMIT,
  PIPELINE_STAGE_LABELS,
  PROGRESS_STEPS,
  canAffordFalCall,
  type Category,
  type PipelineStage,
} from "@ti-amo/shared";
import { RetryActions } from "@/components/RetryActions";

type JobLite = {
  id: string;
  status: string;
  stage: string | null;
  error: string | null;
  category: string;
  metal: string;
  persona: { name: string };
  background: { name: string };
  createdAt: string | Date;
  updatedAt: string | Date;
  apiSpendYen?: number;
};

function progressIndex(stage: string | null | undefined): number {
  if (!stage || stage === "ingest") return 0;
  if (stage === "ready") return PROGRESS_STEPS.length;
  const idx = PROGRESS_STEPS.findIndex((s) => s.key === stage);
  return idx >= 0 ? idx : 0;
}

function remainingCopy(status: string, stage: string | null): string {
  if (status === "queued") return "開始待ちです · 全体の目安 2〜4分";
  switch (stage) {
    case "ingest":
    case "cutout":
      return "およそあと 3〜4分 · 全体の目安 2〜4分";
    case "detail":
      return "およそあと 2〜3分 · 全体の目安 2〜4分";
    case "scene":
      return "およそあと 1〜3分 · 人物シーンがいちばん時間がかかります";
    case "composite":
      return "およそあと 1分 · 全体の目安 2〜4分";
    case "inset":
      return "まもなく完了します";
    default:
      return "全体の目安 2〜4分";
  }
}

function formatElapsed(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m === 0) return `${s}秒`;
  return `${m}分${s.toString().padStart(2, "0")}秒`;
}

export function ProgressPanel({
  job,
  failed,
}: {
  job: JobLite;
  failed: boolean;
}) {
  const current = progressIndex(job.stage);
  const waiting = !failed && job.status === "queued";
  const failAt = failed ? current : -1;
  const pct = failed
    ? Math.max(12, (current / PROGRESS_STEPS.length) * 100)
    : waiting
      ? 6
      : Math.min(95, ((current + 0.45) / PROGRESS_STEPS.length) * 100);
  const stageLabel =
    PIPELINE_STAGE_LABELS[job.stage as PipelineStage] ?? job.stage ?? "処理";
  const createdAt = new Date(job.createdAt).getTime();
  const updatedAt = new Date(job.updatedAt).getTime();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (failed) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [failed]);

  const stuck = !failed && now - updatedAt > 12 * 60 * 1000;
  const spent = job.apiSpendYen ?? 0;
  const costLimited = !canAffordFalCall(spent);

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
            <p className="faint" style={{ fontSize: "0.75rem", margin: "0.5rem auto 0" }}>
              人物生成 約{spent}/{JOB_COST_YEN_LIMIT}円
            </p>
          </>
        ) : (
          <>
            <h1 className="hero-title" style={{ fontSize: "clamp(1.75rem, 4vw, 2.25rem)" }}>
              {waiting ? "開始を待っています" : "生成しています"}
            </h1>
            <p className="muted" style={{ margin: "0.5rem 0 0", fontSize: "0.875rem" }}>
              {CATEGORY_LABELS[job.category as Category] ?? job.category} · {job.metal} ·{" "}
              {job.persona.name} · {job.background.name}
            </p>
            <div className="progress-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}>
              <span style={{ width: `${pct}%` }} />
            </div>
            <p className="progress-eta">
              {remainingCopy(job.status, job.stage)}
              <span className="progress-elapsed">経過 {formatElapsed(now - createdAt)}</span>
            </p>
            <p className="progress-leave">
              この画面を閉じても生成は続きます。一覧からいつでも戻れます。
              {spent > 0 ? ` 人物生成 約${spent}/${JOB_COST_YEN_LIMIT}円。` : ""}
            </p>
          </>
        )}

        <ol className="stage-list">
          {PROGRESS_STEPS.map((step, i) => {
            let cls = "stage-item";
            let mark: string | number = i + 1;
            const isCurrent = !failed && !waiting && i === current;
            if (failed && i === failAt) {
              cls += " failed";
              mark = "!";
            } else if (i < current || (!failed && job.stage === "ready")) {
              cls += " done";
              mark = "✓";
            } else if (isCurrent) {
              cls += " current";
              mark = String(i + 1);
            }
            return (
              <li key={step.key} className={cls}>
                <span className="stage-dot">{mark}</span>
                <span className="stage-copy">
                  <span className="stage-label">
                    {step.label}
                    {failed && i === failAt ? " — 失敗" : ""}
                    {isCurrent ? " · いまここ" : ""}
                  </span>
                  {isCurrent ? <span className="stage-hint">{step.hint}</span> : null}
                  {waiting && i === 0 ? (
                    <span className="stage-hint">ワーカーが動き出すと切り抜きから始まります</span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ol>

        {failed ? (
          <RetryActions jobId={job.id} costLimited={costLimited} />
        ) : stuck ? (
          <RetryActions jobId={job.id} stuck costLimited={costLimited} />
        ) : null}
      </div>
    </div>
  );
}
