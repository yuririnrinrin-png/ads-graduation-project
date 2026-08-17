import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { parsePresetName } from "@/lib/preset-files";
import { requireSession } from "@/lib/session";

type Ctx = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, ctx: Ctx) {
  const { error } = await requireSession();
  if (error) return error;
  const { id } = await ctx.params;

  const existing = await prisma.presetTone.findUnique({ where: { id } });
  if (!existing) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

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

  const tone = await prisma.presetTone.update({
    where: { id },
    data: { name },
  });
  return NextResponse.json({ tone: { id: tone.id, name: tone.name } });
}

export async function DELETE(_req: Request, ctx: Ctx) {
  const { error } = await requireSession();
  if (error) return error;
  const { id } = await ctx.params;

  const existing = await prisma.presetTone.findUnique({ where: { id } });
  if (!existing) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const remaining = await prisma.presetTone.count();
  if (remaining <= 2) {
    return NextResponse.json(
      { error: "全身トーンは最低2つ残してください" },
      { status: 409 }
    );
  }

  const used = await prisma.$queryRaw<{ id: string }[]>`
    SELECT id FROM "Job" WHERE ${id} = ANY("toneIds") LIMIT 1
  `;
  if (used.length > 0) {
    return NextResponse.json(
      { error: "このトーンを使っているジョブがあるので消せません" },
      { status: 409 }
    );
  }

  await prisma.presetTone.delete({ where: { id } });
  return NextResponse.json({ ok: true });
}
