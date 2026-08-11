"use client";

import { FormEvent, useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setPending(true);
    setError(null);
    const fd = new FormData(e.currentTarget);
    const res = await signIn("credentials", {
      username: String(fd.get("username") ?? ""),
      password: String(fd.get("password") ?? ""),
      redirect: false,
    });
    setPending(false);
    if (res?.error) {
      setError("ID またはパスワードが違います");
      return;
    }
    router.push("/");
    router.refresh();
  }

  return (
    <section className="card" style={{ maxWidth: 420, margin: "2rem auto" }}>
      <p className="muted" style={{ letterSpacing: "0.18em", fontSize: 12, textTransform: "uppercase" }}>
        Sign in
      </p>
      <h1 className="hero-title" style={{ fontSize: "2.5rem" }}>
        社内ログイン
      </h1>
      <p className="muted" style={{ marginTop: 0 }}>
        共有アカウントで入ります。ブランド名が最初の画面の主役です。
      </p>
      <form onSubmit={onSubmit} className="stack" style={{ marginTop: "1.5rem" }}>
        <div className="field">
          <label htmlFor="username">ID</label>
          <input id="username" name="username" autoComplete="username" required aria-required="true" defaultValue="ec-team" />
        </div>
        <div className="field">
          <label htmlFor="password">パスワード</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            aria-required="true"
            defaultValue="studio"
          />
        </div>
        {error ? <p className="error">{error}</p> : null}
        <button className="btn btn-primary" type="submit" disabled={pending}>
          {pending ? "確認中…" : "入る"}
        </button>
      </form>
    </section>
  );
}
