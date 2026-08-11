"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  DEFAULT_TRANSFORM,
  SLOT_BADGES,
  SLOT_LABELS,
  type SlotKey,
  type SlotTransform,
} from "@ti-amo/shared";

type Props = {
  jobId: string;
  slot: SlotKey;
  initialTransform?: SlotTransform | null;
  adjustable?: boolean;
};

export function SlotCardClient({
  jobId,
  slot,
  initialTransform,
  adjustable = false,
}: Props) {
  const router = useRouter();
  const [transform, setTransform] = useState<SlotTransform>(
    initialTransform ?? DEFAULT_TRANSFORM
  );
  const [pending, setPending] = useState(false);
  const [bust, setBust] = useState(0);
  const [open, setOpen] = useState(false);

  async function apply(next: SlotTransform) {
    setPending(true);
    const res = await fetch(`/api/jobs/${jobId}/slots/${slot}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    });
    setPending(false);
    if (!res.ok) {
      window.alert("位置の更新に失敗しました");
      return;
    }
    setTransform(next);
    setBust((n) => n + 1);
    router.refresh();
  }

  return (
    <div>
      <div className={`slot-thumb${open ? " slot-thumb-selected" : ""}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/jobs/${jobId}/preview/${slot}?v=${bust}`}
          alt={SLOT_LABELS[slot]}
        />
        <span className="slot-badge">{SLOT_BADGES[slot]}</span>
      </div>
      <div className="slot-card-meta">
        <span>{SLOT_LABELS[slot]}</span>
        <button type="button" className="btn-regen" disabled title="Phase 4">
          再生成
        </button>
      </div>
      {adjustable ? (
        <div className="adjust-panel">
          {!open ? (
            <button type="button" className="btn btn-ghost" style={{ fontSize: "0.75rem", width: "100%", padding: "0.4rem" }} onClick={() => setOpen(true)}>
              大きさ・位置
            </button>
          ) : (
            <>
              <label className="adjust-row">
                <span>大きさ</span>
                <input
                  type="range"
                  min={0.5}
                  max={1.8}
                  step={0.05}
                  value={transform.scale}
                  disabled={pending}
                  onChange={(e) =>
                    setTransform((t) => ({ ...t, scale: Number(e.target.value) }))
                  }
                />
              </label>
              <label className="adjust-row">
                <span>左右</span>
                <input
                  type="range"
                  min={-400}
                  max={400}
                  step={10}
                  value={transform.offsetX}
                  disabled={pending}
                  onChange={(e) =>
                    setTransform((t) => ({ ...t, offsetX: Number(e.target.value) }))
                  }
                />
              </label>
              <label className="adjust-row">
                <span>上下</span>
                <input
                  type="range"
                  min={-400}
                  max={400}
                  step={10}
                  value={transform.offsetY}
                  disabled={pending}
                  onChange={(e) =>
                    setTransform((t) => ({ ...t, offsetY: Number(e.target.value) }))
                  }
                />
              </label>
              <div className="row" style={{ gap: "0.35rem", marginTop: "0.35rem" }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ fontSize: "0.75rem", flex: 1, padding: "0.4rem" }}
                  disabled={pending}
                  onClick={() => setOpen(false)}
                >
                  閉じる
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ fontSize: "0.75rem", flex: 1, padding: "0.4rem" }}
                  disabled={pending}
                  onClick={() => apply(transform)}
                >
                  {pending ? "反映中…" : "確定"}
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
