import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";

export async function GET() {
  const { error } = await requireSession();
  if (error) return error;

  const [personas, backgrounds, tones] = await Promise.all([
    prisma.presetPersona.findMany({ orderBy: { createdAt: "asc" } }),
    prisma.presetBackground.findMany({ orderBy: { createdAt: "asc" } }),
    prisma.presetTone.findMany({ orderBy: { createdAt: "asc" } }),
  ]);

  return NextResponse.json({ personas, backgrounds, tones });
}
