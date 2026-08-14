"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PROGRESS_POLL_MS } from "@ti-amo/shared";

type Props = {
  jobId: string;
  initialStatus: string;
};

/** Poll job status while queued/running; refresh RSC when it changes. */
export function JobStatusPoller({ jobId, initialStatus }: Props) {
  const router = useRouter();
  const [status, setStatus] = useState(initialStatus);
  const [stage, setStage] = useState<string | null>(null);

  useEffect(() => {
    setStatus(initialStatus);
  }, [initialStatus]);

  useEffect(() => {
    if (status === "ready" || status === "failed" || status === "expired") {
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) return;
        const data = await res.json();
        const nextStatus = data.job?.status as string | undefined;
        const nextStage = (data.job?.stage as string | undefined) ?? null;
        if (!nextStatus || cancelled) return;
        if (nextStatus !== status || nextStage !== stage) {
          setStatus(nextStatus);
          setStage(nextStage);
          router.refresh();
        }
      } catch {
        /* ignore transient errors */
      }
    };
    const id = window.setInterval(tick, PROGRESS_POLL_MS);
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [jobId, status, stage, router]);

  return null;
}
