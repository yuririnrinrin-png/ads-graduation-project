"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Props = {
  jobId: string;
  /** After delete, go here instead of refreshing the current page. */
  redirectTo?: string;
};

export function DeleteJobButton({ jobId, redirectTo }: Props) {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function onClick() {
    if (!window.confirm("このジョブを削除しますか？プレビュー画像も消えます。")) {
      return;
    }
    setPending(true);
    const res = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
    setPending(false);
    if (!res.ok) {
      window.alert("削除に失敗しました");
      return;
    }
    if (redirectTo) {
      router.push(redirectTo);
      router.refresh();
      return;
    }
    router.refresh();
  }

  return (
    <button
      type="button"
      className="btn btn-danger-ghost"
      onClick={onClick}
      disabled={pending}
      aria-label="ジョブを削除"
    >
      {pending ? "削除中…" : "削除"}
    </button>
  );
}
