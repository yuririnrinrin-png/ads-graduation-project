import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";

export async function requirePageSession() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/login");
  return session;
}
