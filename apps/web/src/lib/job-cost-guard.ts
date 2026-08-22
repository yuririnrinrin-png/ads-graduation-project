import {
  canAffordFalCall,
  jobCostLimitMessage,
  slotUsesFal,
} from "@ti-amo/shared";

/** Stages that still run fal.ai if the pipeline continues from here. */
function stageWillCallFal(fromStage: string | undefined): boolean {
  const stage = fromStage ?? "ingest";
  return stage !== "composite" && stage !== "inset" && stage !== "ready";
}

export function queueNeedsFal(opts: { fromStage?: string; slots?: string[] }): boolean {
  if (opts.slots?.length) {
    return opts.slots.some((slot) => slotUsesFal(slot));
  }
  return stageWillCallFal(opts.fromStage);
}

export function falBudgetDenied(spentYen: number): string | null {
  if (canAffordFalCall(spentYen)) return null;
  return jobCostLimitMessage(spentYen);
}
