export function isJobBusy(status: string): boolean {
  return status === "queued" || status === "running";
}

export function busyResponse() {
  return { error: "このジョブはすでに処理中です" };
}

export function retryFromStage(status: string, stage: string | null): string {
  if (status !== "failed") return "ingest";
  if (!stage || stage === "ready") return "composite";
  return stage;
}
