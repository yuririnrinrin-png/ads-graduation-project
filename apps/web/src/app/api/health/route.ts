import { prisma } from "@/lib/prisma";

/** Unauthenticated liveness probe for deploy / docker. No secrets. */
export async function GET() {
  try {
    await prisma.$queryRaw`SELECT 1`;
    return Response.json({ ok: true, db: true });
  } catch {
    return Response.json({ ok: false, db: false }, { status: 503 });
  }
}
