"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Props = {
  jobId: string;
  stuck?: boolean;
  costLimited?: boolean;
};

export function RetryActions({ jobId, stuck = false, costLimited = false }: Props) {
  const router = useRouter();
  const [pending, setPending] = useState<"start" | "failed" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function retry(mode: "start" | "failed") {
    setPending(mode);
    setError(null);
    const res = await fetch(`/api/jobs/${jobId}/retry`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, force: stuck }),
    });
    const data = await res.json().catch(() => ({}));
    setPending(null);
    if (!res.ok) {
      setError(data.error ?? "リトライに失敗しました");
      return;
    }
    router.refresh();
  }

  if (costLimited) {
    return (
      <div style={{ marginTop: "2.5rem" }}>
        <p className="error" style={{ margin: 0 }}>
          このジョブの画像生成費が上限の200円に達したため、リトライできません。新しいジョブを作ってください。
        </p>
      </div>
    );
  }

  return (
    <div style={{ marginTop: "2.5rem" }}>
      <div className="row" style={{ justifyContent: "center" }}>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={pending !== null}
          onClick={() => void retry("start")}
        >
          {pending === "start" ? "受付中…" : "最初からリトライ"}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={pending !== null}
          onClick={() => void retry("failed")}
        >
          {pending === "failed"
            ? "受付中…"
            : stuck
              ? "今の段階からやり直す"
              : "失敗した段階からリトライ"}
        </button>
      </div>
      {error ? (
        <p className="error" style={{ marginTop: "0.75rem" }}>
          {error}
        </p>
      ) : (
        <p className="faint" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }}>
          {stuck
            ? "画面が止まったときは、ワーカーを起動し直してからここを押してください。"
            : "同じ写真・設定のままやり直します。ワーカーが起動している必要があります。"}
        </p>
      )}
    </div>
  );
}
