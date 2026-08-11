import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";

export async function GET() {
  const { error } = await requireSession();
  if (error) return error;

  const [personas, backgrounds, tones] = await Promise.all([
    prisma.presetPersona.findMany({ orderBy: { name: "asc" } }),
    prisma.presetBackground.findMany({ orderBy: { name: "asc" } }),
    prisma.presetTone.findMany({ orderBy: { name: "asc" } }),
  ]);

  return NextResponse.json({ personas, backgrounds, tones });
}
