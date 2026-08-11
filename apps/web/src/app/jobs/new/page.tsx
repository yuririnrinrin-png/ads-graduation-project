"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CATEGORIES,
  CATEGORY_LABELS,
  CATEGORY_WEAR_HINTS,
  METALS,
  type Category,
  type Metal,
} from "@ti-amo/shared";

type Presets = {
  personas: { id: string; name: string }[];
  backgrounds: { id: string; name: string }[];
  tones: { id: string; name: string }[];
};

export default function NewJobPage() {
  const router = useRouter();
  const [presets, setPresets] = useState<Presets | null>(null);
  const [category, setCategory] = useState<Category>("bracelet");
  const [metal, setMetal] = useState<Metal>("YG");
  const [personaId, setPersonaId] = useState("");
  const [backgroundId, setBackgroundId] = useState("");
  const [toneIds, setToneIds] = useState<string[]>([]);
  const [mainIndex, setMainIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    fetch("/api/presets")
      .then((r) => r.json())
      .then((data: Presets) => {
        setPresets(data);
        setPersonaId(data.personas[0]?.id ?? "");
        setBackgroundId(data.backgrounds[0]?.id ?? "");
      })
      .catch(() => setError("プリセットの取得に失敗しました"));
  }, []);

  const ready = useMemo(() => {
    return Boolean(category && metal && personaId && backgroundId && toneIds.length === 2);
  }, [category, metal, personaId, backgroundId, toneIds]);

  function toggleTone(id: string) {
    setToneIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return prev;
      return [...prev, id];
    });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setPending(true);
    setError(null);
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category,
        metal,
        mainIndex,
        personaId,
        backgroundId,
        toneIds,
      }),
    });
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
    <section className="stack">
      <div>
        <h1 className="hero-title">新規ジョブ</h1>
        <p className="muted">Phase 1 では画像アップロードはまだなく、プリセット選択だけでダミー10枚 ZIP を作ります。</p>
      </div>

      <form className="card stack" onSubmit={onSubmit}>
        <div className="field">
          <label id="label-category">カテゴリ</label>
          <div className="row" role="group" aria-labelledby="label-category">
            {CATEGORIES.map((c) => (
              <button
                key={c}
                type="button"
                className={`btn ${category === c ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setCategory(c)}
                aria-pressed={category === c}
              >
                {CATEGORY_LABELS[c]}
              </button>
            ))}
          </div>
          <p className="hint">{CATEGORY_WEAR_HINTS[category]}</p>
        </div>

        <div className="field">
          <label id="label-metal">地金カラー</label>
          <div className="row" role="group" aria-labelledby="label-metal">
            {METALS.map((m) => (
              <button
                key={m}
                type="button"
                className={`btn ${metal === m ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setMetal(m)}
                aria-pressed={metal === m}
              >
                {m}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="mainIndex">メイン写真インデックス（0–2）</label>
          <select
            id="mainIndex"
            value={mainIndex}
            onChange={(e) => setMainIndex(Number(e.target.value))}
            aria-required="true"
          >
            <option value={0}>0（1枚目）</option>
            <option value={1}>1（2枚目）</option>
            <option value={2}>2（3枚目）</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="persona">人物プリセット</label>
          <select
            id="persona"
            value={personaId}
            onChange={(e) => setPersonaId(e.target.value)}
            required
            aria-required="true"
            disabled={!presets}
          >
            {(presets?.personas ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="background">背景プリセット</label>
          <select
            id="background"
            value={backgroundId}
            onChange={(e) => setBackgroundId(e.target.value)}
            required
            aria-required="true"
            disabled={!presets}
          >
            {(presets?.backgrounds ?? []).map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <label id="label-tones">全身トーン（ちょうど2つ）</label>
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
                  className={`btn ${selected ? "btn-primary" : "btn-ghost"}`}
                  onClick={() => toggleTone(t.id)}
                  disabled={locked}
                  aria-pressed={selected}
                >
                  {t.name}
                </button>
              );
            })}
          </div>
        </div>

        {!ready ? (
          <p className="muted">必須が揃うまで生成できません（カテゴリ・地金・人物・背景・トーン2つ）。</p>
        ) : null}
        {error ? <p className="error">{error}</p> : null}

        <button className="btn btn-gold" type="submit" disabled={!ready || pending}>
          {pending ? "生成中…" : "ダミー10枚を生成する"}
        </button>
      </form>
    </section>
  );
}
