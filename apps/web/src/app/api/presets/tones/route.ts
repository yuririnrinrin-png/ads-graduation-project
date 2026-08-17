import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { parsePresetName } from "@/lib/preset-files";
import { requireSession } from "@/lib/session";

export async function POST(req: Request) {
  const { error } = await requireSession();
  if (error) return error;

  const body = await req.json().catch(() => null);
  let name: string;
  try {
    name = parsePresetName(body?.name);
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "入力が不正です" },
      { status: 400 }
    );
  }

  const tone = await prisma.presetTone.create({ data: { name } });
  return NextResponse.json({ tone: { id: tone.id, name: tone.name } });
}
