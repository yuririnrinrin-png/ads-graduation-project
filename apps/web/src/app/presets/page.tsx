"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type ImagePreset = {
  id: string;
  name: string;
  hasImage: boolean;
  imageUrl: string | null;
};
type Tone = { id: string; name: string };

type Presets = {
  personas: ImagePreset[];
  backgrounds: ImagePreset[];
  tones: Tone[];
};

export default function PresetsPage() {
  const [data, setData] = useState<Presets | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [bust, setBust] = useState(0);

  const load = useCallback(() => {
    fetch("/api/presets")
      .then((r) => r.json())
      .then((d: Presets) => {
        setData(d);
        setBust(Date.now());
      })
      .catch(() => setError("プリセットの取得に失敗しました"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function addPersona(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    setPending(true);
    setError(null);
    const res = await fetch("/api/presets/personas", { method: "POST", body: fd });
    const json = await res.json();
    setPending(false);
    if (!res.ok) {
      setError(json.error ?? "追加に失敗しました");
      return;
    }
    form.reset();
    load();
  }

  async function addBackground(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    setPending(true);
    setError(null);
    const res = await fetch("/api/presets/backgrounds", { method: "POST", body: fd });
    const json = await res.json();
    setPending(false);
    if (!res.ok) {
      setError(json.error ?? "追加に失敗しました");
      return;
    }
    form.reset();
    load();
  }

  async function addTone(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const name = String(new FormData(form).get("name") ?? "");
    setPending(true);
    setError(null);
    const res = await fetch("/api/presets/tones", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const json = await res.json();
    setPending(false);
    if (!res.ok) {
      setError(json.error ?? "追加に失敗しました");
      return;
    }
    form.reset();
    load();
  }

  async function rename(
    kind: "personas" | "backgrounds" | "tones",
    id: string,
    current: string
  ) {
    const name = window.prompt("新しい名前", current)?.trim();
    if (!name || name === current) return;
    setPending(true);
    setError(null);
    if (kind === "tones") {
      const res = await fetch(`/api/presets/tones/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const json = await res.json();
      setPending(false);
      if (!res.ok) setError(json.error ?? "変更に失敗しました");
      else load();
      return;
    }
    const fd = new FormData();
    fd.set("name", name);
    const res = await fetch(`/api/presets/${kind}/${id}`, { method: "PATCH", body: fd });
    const json = await res.json();
    setPending(false);
    if (!res.ok) setError(json.error ?? "変更に失敗しました");
    else load();
  }

  async function replaceImage(kind: "personas" | "backgrounds", id: string, file: File) {
    const fd = new FormData();
    fd.set("image", file);
    setPending(true);
    setError(null);
    const res = await fetch(`/api/presets/${kind}/${id}`, { method: "PATCH", body: fd });
    const json = await res.json();
    setPending(false);
    if (!res.ok) setError(json.error ?? "画像の更新に失敗しました");
    else load();
  }

  async function remove(kind: "personas" | "backgrounds" | "tones", id: string, label: string) {
    if (!window.confirm(`「${label}」を削除しますか？`)) return;
    setPending(true);
    setError(null);
    const res = await fetch(`/api/presets/${kind}/${id}`, { method: "DELETE" });
    const json = await res.json();
    setPending(false);
    if (!res.ok) setError(json.error ?? "削除に失敗しました");
    else load();
  }

  return (
    <div className="anim-rise">
      <div className="page-head">
        <div>
          <p className="section-kicker">Presets</p>
          <h1 className="section-title">プリセット</h1>
          <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.875rem" }}>
            人物・ディテール背景・全身トーンを追加できます。ジョブで使っているものは消せません。
          </p>
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}

      <section className="frame" style={{ marginBottom: "1.25rem" }}>
        <div className="frame-bar">
          <p className="brand" style={{ fontSize: "1.25rem", margin: 0 }}>
            人物
          </p>
          <span className="faint" style={{ fontSize: "0.75rem" }}>
            {data?.personas.length ?? 0} 人 · 写真なしは生成時に顔を作ります
          </span>
        </div>
        <div className="frame-body stack" style={{ gap: "1rem" }}>
          <div className="persona-grid">
            {(data?.personas ?? []).map((p, idx) => (
              <div key={p.id} className="preset-card">
                <div className={`persona-shot p${idx % 3}`}>
                  {p.imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={`${p.imageUrl}?v=${bust}`} alt="" className="preset-thumb" />
                  ) : null}
                  <span className="persona-name">{p.name}</span>
                </div>
                <div className="row" style={{ gap: "0.35rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="link"
                    disabled={pending}
                    onClick={() => rename("personas", p.id, p.name)}
                  >
                    名前
                  </button>
                  <label className="link" style={{ cursor: "pointer" }}>
                    写真
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      hidden
                      onChange={(ev) => {
                        const file = ev.target.files?.[0];
                        ev.target.value = "";
                        if (file) replaceImage("personas", p.id, file);
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="link"
                    disabled={pending}
                    onClick={() => remove("personas", p.id, p.name)}
                  >
                    削除
                  </button>
                </div>
              </div>
            ))}
          </div>
          <form className="preset-add" onSubmit={addPersona}>
            <input name="name" className="input" required maxLength={40} placeholder="名前（例: Giulia）" />
            <input name="image" type="file" accept="image/jpeg,image/png,image/webp" />
            <button className="btn btn-gold" type="submit" disabled={pending}>
              人物を追加
            </button>
          </form>
        </div>
      </section>

      <section className="frame" style={{ marginBottom: "1.25rem" }}>
        <div className="frame-bar">
          <p className="brand" style={{ fontSize: "1.25rem", margin: 0 }}>
            ディテール背景
          </p>
          <span className="faint" style={{ fontSize: "0.75rem" }}>
            {data?.backgrounds.length ?? 0} 件 · 写真を上げるとディテール3枚の背景になります
          </span>
        </div>
        <div className="frame-body stack" style={{ gap: "1rem" }}>
          <div className="bg-grid">
            {(data?.backgrounds ?? []).map((b, idx) => (
              <div key={b.id} className="preset-card">
                <div
                  className={`bg-tile ${["marble-a", "marble-b", "linen", "marble-c"][idx % 4]}`}
                  style={
                    b.imageUrl
                      ? { backgroundImage: `url(${b.imageUrl}?v=${bust})`, backgroundSize: "cover" }
                      : undefined
                  }
                  title={b.name}
                />
                <p className="muted" style={{ fontSize: "0.75rem", margin: 0 }}>
                  {b.name}
                </p>
                <div className="row" style={{ gap: "0.35rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="link"
                    disabled={pending}
                    onClick={() => rename("backgrounds", b.id, b.name)}
                  >
                    名前
                  </button>
                  <label className="link" style={{ cursor: "pointer" }}>
                    写真
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      hidden
                      onChange={(ev) => {
                        const file = ev.target.files?.[0];
                        ev.target.value = "";
                        if (file) replaceImage("backgrounds", b.id, file);
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="link"
                    disabled={pending}
                    onClick={() => remove("backgrounds", b.id, b.name)}
                  >
                    削除
                  </button>
                </div>
              </div>
            ))}
          </div>
          <form className="preset-add" onSubmit={addBackground}>
            <input name="name" className="input" required maxLength={40} placeholder="名前（例: ベージュ石）" />
            <input name="image" type="file" accept="image/jpeg,image/png,image/webp" />
            <button className="btn btn-gold" type="submit" disabled={pending}>
              背景を追加
            </button>
          </form>
        </div>
      </section>

      <section className="frame">
        <div className="frame-bar">
          <p className="brand" style={{ fontSize: "1.25rem", margin: 0 }}>
            全身トーン
          </p>
          <span className="faint" style={{ fontSize: "0.75rem" }}>
            {data?.tones.length ?? 0} 件 · ジョブではちょうど2つ選びます
          </span>
        </div>
        <div className="frame-body stack" style={{ gap: "1rem" }}>
          <div className="row" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            {(data?.tones ?? []).map((t) => (
              <div key={t.id} className="chip-row">
                <span className="chip" aria-pressed="true">
                  {t.name}
                </span>
                <button
                  type="button"
                  className="link"
                  disabled={pending}
                  onClick={() => rename("tones", t.id, t.name)}
                >
                  名前
                </button>
                <button
                  type="button"
                  className="link"
                  disabled={pending}
                  onClick={() => remove("tones", t.id, t.name)}
                >
                  削除
                </button>
              </div>
            ))}
          </div>
          <form className="preset-add" onSubmit={addTone}>
            <input name="name" className="input" required maxLength={40} placeholder="名前（例: フォーマル）" />
            <button className="btn btn-gold" type="submit" disabled={pending}>
              トーンを追加
            </button>
          </form>
        </div>
      </section>
    </div>
  );
}
