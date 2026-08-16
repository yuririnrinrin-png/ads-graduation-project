"use client";

import { useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useRouter } from "next/navigation";
import {
  CANVAS_SIZE,
  DEFAULT_TRANSFORM,
  DETAIL_SLOTS,
  TRANSFORM_OFFSET_LIMIT,
  TRANSFORM_ROTATE_LIMIT,
  getAnchors,
  SLOT_BADGES,
  SLOT_LABELS,
  type Category,
  type DetailSlot,
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
  insetSlot?: DetailSlot;
  /** Changes after regen so the browser does not keep the old JPEG. */
  imageVersion?: number;
};

const MIN_SCALE = 0.4;
const MAX_SCALE = 2.2;
const MAX_OFFSET = TRANSFORM_OFFSET_LIMIT;
const MAX_ROTATE = TRANSFORM_ROTATE_LIMIT;

function clampTransform(t: SlotTransform): SlotTransform {
  return {
    scale: Math.min(MAX_SCALE, Math.max(MIN_SCALE, t.scale)),
    offsetX: Math.min(MAX_OFFSET, Math.max(-MAX_OFFSET, t.offsetX)),
    offsetY: Math.min(MAX_OFFSET, Math.max(-MAX_OFFSET, t.offsetY)),
    rotate: Math.min(MAX_ROTATE, Math.max(-MAX_ROTATE, t.rotate ?? 0)),
    hidden: Boolean(t.hidden),
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
  insetSlot,
  imageVersion = 0,
}: Props) {
  const router = useRouter();
  const anchors = category ? getAnchors(category, body) : getAnchors("bracelet", body);

  const [transforms, setTransforms] = useState<SlotTransform[]>(() =>
    anchors.map((_, i) => initialTransforms?.[i] ?? DEFAULT_TRANSFORM)
  );
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [bust, setBust] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const transformsRef = useRef(transforms);
  transformsRef.current = transforms;

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
    void commit(transformsRef.current);
  }

  function reset() {
    const next = anchors.map(() => ({ ...DEFAULT_TRANSFORM }));
    setTransforms(next);
    void commit(next);
  }

  function toggleHidden(i: number) {
    if (pending) return;
    const current = transforms[i];
    if (!current) return;
    if (!current.hidden) {
      const visible = transforms.filter((t) => !t.hidden).length;
      if (visible <= 1) {
        window.alert("両方消すことはできません。片方だけ消せます。");
        return;
      }
    }
    const next = transforms.map((t, idx) =>
      idx === i ? { ...t, hidden: !t.hidden } : t
    );
    setTransforms(next);
    void commit(next);
  }

  async function regen() {
    setPending(true);
    const res = await fetch(`/api/jobs/${jobId}/slots/${slot}/regen`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    setPending(false);
    setConfirming(false);
    if (!res.ok) {
      window.alert(data.error ?? "再生成に失敗しました");
      return;
    }
    router.refresh();
  }

  async function changeInset(next: DetailSlot) {
    if (next === insetSlot) return;
    setPending(true);
    const res = await fetch(`/api/jobs/${jobId}/inset`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ insetSlot: next }),
    });
    const data = await res.json().catch(() => ({}));
    setPending(false);
    if (!res.ok) {
      window.alert(data.error ?? "インセットの更新に失敗しました");
      return;
    }
    router.refresh();
  }

  if (!adjustable || !editing) {
    return (
      <div>
        <div className="slot-thumb">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/api/jobs/${jobId}/preview/${slot}?v=${imageVersion}-${bust}`} alt={SLOT_LABELS[slot]} />
          <span className="slot-badge">{SLOT_BADGES[slot]}</span>
        </div>
        <div className="slot-card-meta">
          <span>{SLOT_LABELS[slot]}</span>
          {confirming ? (
            <span className="regen-confirm">
              <button type="button" className="btn-regen" disabled={pending} onClick={() => void regen()}>
                {pending ? "受付中…" : "する"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                style={{ fontSize: "0.7rem", padding: "0.2rem 0.45rem" }}
                disabled={pending}
                onClick={() => setConfirming(false)}
              >
                やめる
              </button>
            </span>
          ) : (
            <button type="button" className="btn-regen" disabled={pending} onClick={() => setConfirming(true)}>
              再生成
            </button>
          )}
        </div>
        {confirming ? (
          <p className="faint" style={{ margin: "0.35rem 0 0", fontSize: "0.7rem" }}>
            {SLOT_LABELS[slot]} を再生成しますか？人物は同じプリセットのままです。
          </p>
        ) : null}
        {slot === "wide_inset" ? (
          <label className="inset-pick">
            インセット元
            <select
              value={insetSlot ?? "detail_a"}
              disabled={pending}
              onChange={(e) => void changeInset(e.target.value as DetailSlot)}
            >
              {DETAIL_SLOTS.map((key) => (
                <option key={key} value={key}>
                  {SLOT_LABELS[key]}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {adjustable ? (
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: "0.75rem", width: "100%", padding: "0.4rem", marginTop: "0.5rem" }}
            onClick={() => setEditing(true)}
          >
            {category === "earring"
              ? "大きさ・位置・回転・片方を消す"
              : "大きさ・位置・回転を調整"}
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
          src={`/api/jobs/${jobId}/scene/${slot}?v=${imageVersion}`}
          alt=""
          className="edit-canvas-bg"
          draggable={false}
        />
        {anchors.map((anchor, i) => {
          const t = transforms[i] ?? DEFAULT_TRANSFORM;
          const widthPct = anchor.scale * t.scale * 100;
          const cxPct = anchor.x * 100 + (t.offsetX / CANVAS_SIZE) * 100;
          const cyPct = anchor.y * 100 + (t.offsetY / CANVAS_SIZE) * 100;
          const deg = (anchor.rotate ?? 0) + (t.rotate ?? 0);
          if (t.hidden) {
            return (
              <span
                key={i}
                className="edit-jewel-ghost"
                style={{
                  left: `${cxPct - widthPct / 2}%`,
                  top: `${cyPct - widthPct / 2}%`,
                  width: `${widthPct}%`,
                  height: `${widthPct}%`,
                }}
              />
            );
          }
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
                transform: `${i % 2 === 1 ? "scaleX(-1) " : ""}rotate(${deg}deg)`,
              }}
            />
          );
        })}
        {anchors.map((anchor, i) => {
          const t = transforms[i] ?? DEFAULT_TRANSFORM;
          if (t.hidden) return null;
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
          ? "左右それぞれドラッグで移動 · 丸のつまみでサイズ · スライダーで一周回転"
          : "ジュエリーをドラッグで移動 · 右下の丸で大きさ · スライダーで一周回転"}
        {category === "earring"
          ? " · 横顔では見えない側を消せます"
          : ""}
      </p>
      {category === "earring" ? (
        <div className="row" style={{ gap: "0.35rem", marginTop: "0.45rem" }}>
          {anchors.map((_, i) => {
            const t = transforms[i] ?? DEFAULT_TRANSFORM;
            const side = i === 0 ? "左" : "右";
            return (
              <button
                key={i}
                type="button"
                className="btn btn-ghost"
                style={{ fontSize: "0.75rem", flex: 1, padding: "0.4rem" }}
                disabled={pending}
                onClick={() => toggleHidden(i)}
              >
                {t.hidden ? `${side}を戻す` : `${side}を消す`}
              </button>
            );
          })}
        </div>
      ) : null}
      <div className="row" style={{ gap: "0.65rem", marginTop: "0.45rem", alignItems: "center" }}>
        {anchors.map((_, i) => {
          const t = transforms[i] ?? DEFAULT_TRANSFORM;
          const label = multi ? (i === 0 ? "左の回転" : "右の回転") : "回転";
          return (
            <label
              key={i}
              className="faint"
              style={{ display: "grid", gap: "0.15rem", fontSize: "0.7rem", flex: 1 }}
            >
              {label} {Math.round(t.rotate ?? 0)}°
              <input
                type="range"
                min={-MAX_ROTATE}
                max={MAX_ROTATE}
                step={1}
                value={t.rotate ?? 0}
                disabled={pending || t.hidden}
                aria-label={label}
                onChange={(e) => {
                  const rotate = Number(e.target.value);
                  setTransforms((prev) =>
                    prev.map((x, idx) => (idx === i ? clampTransform({ ...x, rotate }) : x))
                  );
                }}
                onPointerUp={() => void commit(transformsRef.current)}
                onKeyUp={() => void commit(transformsRef.current)}
              />
            </label>
          );
        })}
      </div>
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
