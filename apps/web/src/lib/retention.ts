import { JOB_RETENTION_DAYS } from "@ti-amo/shared";

const DAY_MS = 24 * 60 * 60 * 1000;

export function expiryDate(createdAt: Date, expiresAt: Date | null): Date {
  if (expiresAt) return expiresAt;
  const d = new Date(createdAt);
  d.setDate(d.getDate() + JOB_RETENTION_DAYS);
  return d;
}

/** Whole days left until files are deleted. 0 or less means due now. */
export function remainingDays(
  createdAt: Date,
  expiresAt: Date | null,
  now = new Date()
): number {
  return Math.ceil((expiryDate(createdAt, expiresAt).getTime() - now.getTime()) / DAY_MS);
}

export function retentionLabel(
  createdAt: Date,
  expiresAt: Date | null,
  status?: string,
  now = new Date()
): string {
  if (status === "expired") return "期限切れ（画像は削除済み）";
  const days = remainingDays(createdAt, expiresAt, now);
  if (days <= 0) return "本日削除";
  if (days === 1) return "残り1日";
  return `残り${days}日`;
}

export function isPastExpiry(
  createdAt: Date,
  expiresAt: Date | null,
  status?: string,
  now = new Date()
): boolean {
  if (status === "expired") return true;
  return remainingDays(createdAt, expiresAt, now) <= 0;
}
