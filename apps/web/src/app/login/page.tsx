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
    <div className="login-split anim-rise">
      <div className="login-brand">
        <div>
          <p className="login-brand-title">
            Ti amo
            <br />
            Jewelry
            <br />
            Studio
          </p>
          <p className="login-brand-copy">
            イタリアンゴールドジュエリーの商品ページ用写真を、型どおり10枚そろえる。
          </p>
        </div>
        <p className="login-brand-foot">Internal · EC Ops</p>
      </div>

      <div className="login-panel">
        <div className="login-panel-inner">
          <p className="login-eyebrow">Sign in</p>
          <h1 className="hero-title" style={{ fontSize: "1.875rem", marginTop: "0.5rem" }}>
            社内ログイン
          </h1>
          <form onSubmit={onSubmit} className="stack" style={{ marginTop: "2rem", gap: "1rem" }}>
            <div className="field">
              <label htmlFor="username">ID</label>
              <input
                id="username"
                name="username"
                autoComplete="username"
                required
                aria-required="true"
                defaultValue="ec-team"
              />
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
            <button className="btn btn-primary" type="submit" disabled={pending} style={{ width: "100%" }}>
              {pending ? "確認中…" : "入る"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
