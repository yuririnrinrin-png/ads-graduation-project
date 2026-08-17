import type { Metadata } from "next";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ti amo Jewelry Studio",
  description: "EC商品写真を型どおり10枚そろえる社内ツール",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getServerSession(authOptions);

  return (
    <html lang="ja">
      <body>
        <div className="app-shell">
          {session ? (
            <>
              <header className="topbar">
                <a href="/" className="brand">
                  Ti amo Jewelry Studio
                </a>
                <div className="topbar-right">
                  <a className="link" href="/">
                    ジョブ
                  </a>
                  <a className="link" href="/presets">
                    プリセット
                  </a>
                  <span>{session.user?.name}</span>
                  <a className="link" href="/api/auth/signout">
                    出る
                  </a>
                </div>
              </header>
              <main className="main">{children}</main>
            </>
          ) : (
            <main className="main-auth">{children}</main>
          )}
        </div>
      </body>
    </html>
  );
}
