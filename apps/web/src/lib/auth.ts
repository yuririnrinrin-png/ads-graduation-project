import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "Shared studio login",
      credentials: {
        username: { label: "ID", type: "text" },
        password: { label: "パスワード", type: "password" },
      },
      async authorize(credentials) {
        const user = process.env.AUTH_USER ?? "ec-team";
        const pass = process.env.AUTH_PASSWORD ?? "studio";
        if (
          credentials?.username === user &&
          credentials?.password === pass
        ) {
          return { id: "shared", name: user };
        }
        return null;
      },
    }),
  ],
  session: { strategy: "jwt" },
  pages: {
    signIn: "/login",
  },
  secret: process.env.NEXTAUTH_SECRET,
};
