"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CATEGORIES,
  CATEGORY_LABELS,
  CATEGORY_WEAR_HINTS,
  DETAIL_SLOTS,
  METALS,
  SLOT_LABELS,
  type Category,
  type DetailSlot,
  type Metal,
} from "@ti-amo/shared";

type Presets = {
  personas: { id: string; name: string }[];
  backgrounds: { id: string; name: string }[];
  tones: { id: string; name: string }[];
};

const BG_CLASS = ["marble-a", "marble-b", "linen", "marble-c"] as const;

export default function NewJobPage() {
  const router = useRouter();
  const [presets, setPresets] = useState<Presets | null>(null);
  const [category, setCategory] = useState<Category | null>(null);
  const [metal, setMetal] = useState<Metal | null>(null);
  const [personaId, setPersonaId] = useState("");
  const [backgroundId, setBackgroundId] = useState("");
  const [toneIds, setToneIds] = useState<string[]>([]);
  const [insetSlot, setInsetSlot] = useState<DetailSlot>("detail_a");
  const [mainIndex, setMainIndex] = useState(0);
  const [images, setImages] = useState<(File | null)[]>([null, null, null]);
  const [previews, setPreviews] = useState<(string | null)[]>([null, null, null]);
  /** Bump per-slot to reset `<input type="file">` after clear so the same file can be re-picked. */
  const [fileInputKeys, setFileInputKeys] = useState([0, 0, 0]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    fetch("/api/presets")
      .then((r) => r.json())
      .then((data: Presets) => setPresets(data))
      .catch(() => setError("プリセットの取得に失敗しました"));
  }, []);

  useEffect(() => {
    return () => {
      previews.forEach((url) => {
        if (url) URL.revokeObjectURL(url);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const missing = useMemo(() => {
    const items: string[] = [];
    if (images.some((f) => !f)) items.push("商品写真3枚");
    if (!category) items.push("カテゴリ");
    if (!metal) items.push("地金カラー");
    if (!personaId) items.push("人物プリセット");
    if (!backgroundId) items.push("ディテール背景");
    if (toneIds.length !== 2) items.push("全身トーン（ちょうど2つ）");
    return items;
  }, [images, category, metal, personaId, backgroundId, toneIds]);

  const ready = missing.length === 0;

  function setImageAt(index: number, file: File | null) {
    setImages((prev) => {
      const next = [...prev];
      next[index] = file;
      return next;
    });
    setPreviews((prev) => {
      const next = [...prev];
      if (next[index]) URL.revokeObjectURL(next[index]!);
      next[index] = file ? URL.createObjectURL(file) : null;
      return next;
    });
  }

  function clearImageAt(index: number) {
    if (!window.confirm(`商品写真${index + 1}を消去しますか？`)) {
      return;
    }
    setImageAt(index, null);
    setFileInputKeys((prev) => {
      const next = [...prev];
      next[index] += 1;
      return next;
    });
    setMainIndex((current) => {
      if (current !== index) return current;
      const remaining = images
        .map((f, i) => (i !== index && f ? i : -1))
        .filter((i) => i >= 0);
      return remaining[0] ?? 0;
    });
  }

  function toggleTone(id: string) {
    setToneIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return prev;
      return [...prev, id];
    });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ready || !category || !metal) return;
    setPending(true);
    setError(null);

    const fd = new FormData();
    fd.set("category", category);
    fd.set("metal", metal);
    fd.set("mainIndex", String(mainIndex));
    fd.set("personaId", personaId);
    fd.set("backgroundId", backgroundId);
    fd.set("toneIds", JSON.stringify(toneIds));
    fd.set("insetSlot", insetSlot);
    images.forEach((file, i) => {
      if (file) fd.set(`image${i}`, file);
    });

    const res = await fetch("/api/jobs", { method: "POST", body: fd });
    const data = await res.json();
    setPending(false);
    if (!res.ok) {
      setError(data.error ?? "作成に失敗しました");
      return;
    }
    router.push(`/jobs/${data.job.id}`);
    router.refresh();
  }

  return (
    <div className="anim-rise">
      <div className="page-head">
        <div>
          <p className="section-kicker">New job</p>
          <h1 className="section-title">新規ジョブ</h1>
        </div>
        <span className="pill-tag">NEW JOB</span>
      </div>

      <form className="frame" onSubmit={onSubmit}>
        <div className="frame-bar">
          <div className="row" style={{ gap: "0.75rem" }}>
            <span className="brand" style={{ fontSize: "1.25rem" }}>
              Ti amo Jewelry Studio
            </span>
            <span className="pill-tag">PHASE 4</span>
          </div>
          <span className="faint" style={{ fontSize: "0.75rem" }}>
            商品3枚 → 10枚生成 → レビューで直す
          </span>
        </div>

        <div className="frame-body job-grid">
          <div className="stack" style={{ gap: "1rem" }}>
            <div>
              <h2 className="section-title" style={{ fontSize: "1.25rem" }}>
                商品写真 3枚
              </h2>
              <p className="muted" style={{ fontSize: "0.75rem", margin: "0.35rem 0 0" }}>
                同一商品・白〜淡色背景・角度違い。順序がディテール1〜3。サムネを選ぶとメイン切替。JPEG / PNG / WebP・各12MBまで。
              </p>
              <p className="muted" style={{ fontSize: "0.75rem", margin: "0.35rem 0 0" }}>
                着用に使うメイン写真は、できるだけ正面から撮った1枚を選んでください。斜めでも生成はできます。
              </p>
            </div>

            <div className="upload-grid" role="radiogroup" aria-label="メイン写真">
              {[0, 1, 2].map((i) => {
                const selected = mainIndex === i;
                const preview = previews[i];
                return (
                  <div key={i} style={{ display: "grid", gap: "0.35rem" }}>
                    <button
                      type="button"
                      className="upload-tile"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setMainIndex(i)}
                      disabled={!images[i]}
                    >
                      <span className="upload-tile-num">
                        {selected && images[i] ? `${i + 1} · MAIN` : String(i + 1)}
                      </span>
                      {preview ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={preview}
                          alt={`商品写真${i + 1}`}
                          style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        />
                      ) : (
                        <span className="upload-tile-body">
                          <span style={{ fontSize: "1.5rem", color: "var(--gold)" }}>◇</span>
                          未選択
                        </span>
                      )}
                      {images[i] && !selected ? (
                        <span className="upload-tile-cta">メインにする</span>
                      ) : null}
                    </button>
                    <div className="row" style={{ gap: "0.35rem" }}>
                      <label
                        className="btn btn-ghost"
                        style={{ fontSize: "0.75rem", padding: "0.45rem", flex: 1 }}
                      >
                        {images[i] ? "差し替え" : "ファイルを選ぶ"}
                        <input
                          key={fileInputKeys[i]}
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          hidden
                          aria-label={`商品写真${i + 1}`}
                          onChange={(e) => setImageAt(i, e.target.files?.[0] ?? null)}
                        />
                      </label>
                      {images[i] ? (
                        <button
                          type="button"
                          className="btn btn-danger-ghost"
                          style={{ fontSize: "0.75rem", padding: "0.45rem 0.65rem" }}
                          onClick={() => clearImageAt(i)}
                          aria-label={`商品写真${i + 1}を消去`}
                        >
                          消去
                        </button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="muted" style={{ fontSize: "0.75rem", margin: 0 }}>
              メイン写真:{" "}
              <strong style={{ color: "var(--ink)", fontWeight: 500 }}>{mainIndex + 1}枚目</strong>{" "}
              を着用合成に使用（Phase 3）
            </p>
          </div>

          <div className="stack" style={{ gap: "1.5rem" }}>
            <div
              style={{
                display: "grid",
                gap: "1rem",
                gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))",
              }}
            >
              <div className="field">
                <p className="field-label" id="label-category">
                  カテゴリ
                </p>
                <div className="row" role="group" aria-labelledby="label-category">
                  {CATEGORIES.map((c) => (
                    <button
                      key={c}
                      type="button"
                      className="chip"
                      aria-pressed={category === c}
                      onClick={() => setCategory(c)}
                    >
                      {CATEGORY_LABELS[c]}
                    </button>
                  ))}
                </div>
                {category ? <p className="hint">{CATEGORY_WEAR_HINTS[category]}</p> : null}
              </div>

              <div className="field">
                <p className="field-label" id="label-metal">
                  地金カラー
                </p>
                <div className="row" role="group" aria-labelledby="label-metal">
                  {METALS.map((m) => (
                    <button
                      key={m}
                      type="button"
                      className="chip"
                      aria-pressed={metal === m}
                      onClick={() => setMetal(m)}
                    >
                      <span className={`metal-dot ${m.toLowerCase()}`} aria-hidden />
                      {m}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="field">
              <p className="field-label" id="label-persona">
                人物プリセット（1人選ぶ · このジョブ内で固定）
              </p>
              <div className="persona-grid" role="group" aria-labelledby="label-persona">
                {(presets?.personas ?? []).map((p, idx) => (
                  <button
                    key={p.id}
                    type="button"
                    className="persona-card"
                    aria-pressed={personaId === p.id}
                    onClick={() => setPersonaId(p.id)}
                  >
                    <div className={`persona-shot p${idx % 3}`}>
                      <span className="persona-name">{p.name}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="field">
              <p className="field-label" id="label-bg">
                ディテール背景（3枚で統一）
              </p>
              <div className="bg-grid" role="group" aria-labelledby="label-bg">
                {(presets?.backgrounds ?? []).map((b, idx) => (
                  <button
                    key={b.id}
                    type="button"
                    className={`bg-tile ${BG_CLASS[idx % BG_CLASS.length]}`}
                    aria-pressed={backgroundId === b.id}
                    aria-label={b.name}
                    title={b.name}
                    onClick={() => setBackgroundId(b.id)}
                  />
                ))}
              </div>
              <p className="muted" style={{ fontSize: "0.75rem", margin: 0 }}>
                {(presets?.backgrounds ?? []).map((b) => b.name).join(" · ") || "読み込み中…"}
              </p>
            </div>

            <div className="field">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <p className="field-label" id="label-tones" style={{ margin: 0 }}>
                  全身トーン（ちょうど2つ）
                </p>
                <span className="hint">{toneIds.length}/2 選択中</span>
              </div>
              <div className="row" role="group" aria-labelledby="label-tones">
                {(presets?.tones ?? []).map((t) => {
                  const selected = toneIds.includes(t.id);
                  const locked = !selected && toneIds.length >= 2;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      className="chip"
                      aria-pressed={selected}
                      aria-disabled={locked}
                      disabled={locked}
                      onClick={() => toggleTone(t.id)}
                    >
                      {t.name}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="field">
              <p className="field-label" id="label-inset">
                インセットに使うディテール（任意・あとから変更可）
              </p>
              <div className="row" role="group" aria-labelledby="label-inset">
                {DETAIL_SLOTS.map((key) => (
                  <button
                    key={key}
                    type="button"
                    className="chip"
                    aria-pressed={insetSlot === key}
                    onClick={() => setInsetSlot(key)}
                  >
                    {SLOT_LABELS[key]}
                  </button>
                ))}
              </div>
            </div>

            <div className="submit-row">
              {ready ? (
                <>
                  <p className="muted" style={{ fontSize: "0.75rem", margin: 0 }}>
                    必須が揃っています → 生成可能
                  </p>
                  <button className="btn btn-gold" type="submit" disabled={pending}>
                    {pending ? "受付中…" : "10枚を生成する"}
                  </button>
                </>
              ) : (
                <div className="guide-box" style={{ width: "100%" }}>
                  <p className="muted" style={{ fontSize: "0.75rem", margin: 0, color: "var(--ink-soft)" }}>
                    不足: {missing.join("・") || "読み込み中"}
                  </p>
                  <button className="btn btn-gold" type="submit" disabled>
                    10枚を生成する
                  </button>
                </div>
              )}
            </div>
            {error ? <p className="error">{error}</p> : null}
          </div>
        </div>
      </form>
    </div>
  );
}
