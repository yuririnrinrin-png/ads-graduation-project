import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { publicPreset } from "@/lib/preset-files";
import { requireSession } from "@/lib/session";

export async function GET() {
  const { error } = await requireSession();
  if (error) return error;

  const [personas, backgrounds, tones] = await Promise.all([
    prisma.presetPersona.findMany({ orderBy: { createdAt: "asc" } }),
    prisma.presetBackground.findMany({ orderBy: { createdAt: "asc" } }),
    prisma.presetTone.findMany({ orderBy: { createdAt: "asc" } }),
  ]);

  return NextResponse.json({
    personas: personas.map((p) => publicPreset(p, "personas")),
    backgrounds: backgrounds.map((b) => publicPreset(b, "backgrounds")),
    tones: tones.map((t) => ({ id: t.id, name: t.name })),
  });
}
