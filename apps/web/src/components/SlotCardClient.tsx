"use client";

import { useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useRouter } from "next/navigation";
import {
  CANVAS_SIZE,
  DEFAULT_TRANSFORM,
  getAnchors,
  SLOT_BADGES,
  SLOT_LABELS,
  type Category,
  type SlotKey,
  type SlotTransform,
} from "@ti-amo/shared";

type Props = {
  jobId: string;
  slot: SlotKey;
  initialTransforms?: SlotTransform[] | null;
  adjustable?: boolean;
  /** Needed only when adjustable=true, to pick anchor points for the drag overlay. */
  category?: Category;
  body?: boolean;
};

const MIN_SCALE = 0.4;
const MAX_SCALE = 2.2;
const MAX_OFFSET = 550;

function clampTransform(t: SlotTransform): SlotTransform {
  return {
    scale: Math.min(MAX_SCALE, Math.max(MIN_SCALE, t.scale)),
    offsetX: Math.min(MAX_OFFSET, Math.max(-MAX_OFFSET, t.offsetX)),
    offsetY: Math.min(MAX_OFFSET, Math.max(-MAX_OFFSET, t.offsetY)),
  };
}

type DragState = {
  anchorIndex: number;
  mode: "move" | "resize";
  startX: number;
  startY: number;
  start: SlotTransform;
};

export function SlotCardClient({
  jobId,
  slot,
  initialTransforms,
  adjustable = false,
  category,
  body = false,
}: Props) {
  const router = useRouter();
  const anchors = category ? getAnchors(category, body) : getAnchors("bracelet", body);

  const [transforms, setTransforms] = useState<SlotTransform[]>(() =>
    anchors.map((_, i) => initialTransforms?.[i] ?? DEFAULT_TRANSFORM)
  );
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [bust, setBust] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);

  async function commit(next: SlotTransform[]) {
    setPending(true);
    const res = await fetch(`/api/jobs/${jobId}/slots/${slot}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transforms: next }),
    });
    setPending(false);
    if (!res.ok) {
      window.alert("位置の更新に失敗しました");
      return;
    }
    setBust((n) => n + 1);
    router.refresh();
  }

  function startMove(i: number, e: ReactPointerEvent) {
    if (pending) return;
    e.preventDefault();
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    dragRef.current = {
      anchorIndex: i,
      mode: "move",
      startX: e.clientX,
      startY: e.clientY,
      start: transforms[i],
    };
  }

  function startResize(i: number, e: ReactPointerEvent) {
    if (pending) return;
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    dragRef.current = {
      anchorIndex: i,
      mode: "resize",
      startX: e.clientX,
      startY: e.clientY,
      start: transforms[i],
    };
  }

  function onPointerMove(e: ReactPointerEvent) {
    const drag = dragRef.current;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!drag || !rect) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    let next: SlotTransform;
    if (drag.mode === "move") {
      next = clampTransform({
        ...drag.start,
        offsetX: drag.start.offsetX + (dx / rect.width) * CANVAS_SIZE,
        offsetY: drag.start.offsetY + (dy / rect.height) * CANVAS_SIZE,
      });
    } else {
      const deltaScale = (dx / rect.width) * 2.4;
      next = clampTransform({ ...drag.start, scale: drag.start.scale + deltaScale });
    }
    setTransforms((prev) => prev.map((t, i) => (i === drag.anchorIndex ? next : t)));
  }

  function endDrag() {
    if (!dragRef.current) return;
    dragRef.current = null;
    void commit(transforms);
  }

  function reset() {
    const next = anchors.map(() => DEFAULT_TRANSFORM);
    setTransforms(next);
    void commit(next);
  }

  if (!adjustable || !editing) {
    return (
      <div>
        <div className="slot-thumb">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/api/jobs/${jobId}/preview/${slot}?v=${bust}`} alt={SLOT_LABELS[slot]} />
          <span className="slot-badge">{SLOT_BADGES[slot]}</span>
        </div>
        <div className="slot-card-meta">
          <span>{SLOT_LABELS[slot]}</span>
          <button type="button" className="btn-regen" disabled title="Phase 4">
            再生成
          </button>
        </div>
        {adjustable ? (
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: "0.75rem", width: "100%", padding: "0.4rem", marginTop: "0.5rem" }}
            onClick={() => setEditing(true)}
          >
            大きさ・位置をドラッグ調整
          </button>
        ) : null}
      </div>
    );
  }

  const multi = anchors.length > 1;

  return (
    <div>
      <div
        ref={containerRef}
        className="edit-canvas"
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/jobs/${jobId}/scene/${slot}`}
          alt=""
          className="edit-canvas-bg"
          draggable={false}
        />
        {anchors.map((anchor, i) => {
          const t = transforms[i] ?? DEFAULT_TRANSFORM;
          const widthPct = anchor.scale * t.scale * 100;
          const cxPct = anchor.x * 100 + (t.offsetX / CANVAS_SIZE) * 100;
          const cyPct = anchor.y * 100 + (t.offsetY / CANVAS_SIZE) * 100;
          return (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={i}
              src={`/api/jobs/${jobId}/cutout/main`}
              alt=""
              draggable={false}
              className="edit-jewel"
              onPointerDown={(e) => startMove(i, e)}
              style={{
                left: `${cxPct - widthPct / 2}%`,
                top: `${cyPct - widthPct / 2}%`,
                width: `${widthPct}%`,
                transform: i % 2 === 1 ? "scaleX(-1)" : undefined,
              }}
            />
          );
        })}
        {anchors.map((anchor, i) => {
          const t = transforms[i] ?? DEFAULT_TRANSFORM;
          const widthPct = anchor.scale * t.scale * 100;
          const cxPct = anchor.x * 100 + (t.offsetX / CANVAS_SIZE) * 100;
          const cyPct = anchor.y * 100 + (t.offsetY / CANVAS_SIZE) * 100;
          return (
            <span
              key={i}
              className="edit-resize-handle"
              onPointerDown={(e) => startResize(i, e)}
              style={{
                left: `${cxPct + widthPct / 2}%`,
                top: `${cyPct + widthPct / 2}%`,
              }}
            />
          );
        })}
      </div>
      <p className="faint" style={{ margin: "0.4rem 0 0", fontSize: "0.7rem" }}>
        {multi
          ? "左右それぞれドラッグで移動 · 丸のつまみで個別にサイズ調整"
          : "ジュエリーをドラッグで移動 · 右下の丸をドラッグで大きさ調整"}
      </p>
      <div className="row" style={{ gap: "0.35rem", marginTop: "0.4rem" }}>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ fontSize: "0.75rem", flex: 1, padding: "0.4rem" }}
          disabled={pending}
          onClick={reset}
        >
          リセット
        </button>
        <button
          type="button"
          className="btn btn-primary"
          style={{ fontSize: "0.75rem", flex: 1, padding: "0.4rem" }}
          disabled={pending}
          onClick={() => setEditing(false)}
        >
          {pending ? "反映中…" : "完了"}
        </button>
      </div>
    </div>
  );
}
