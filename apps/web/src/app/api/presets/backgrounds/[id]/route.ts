import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  parsePresetName,
  publicPreset,
  removePresetImage,
  savePresetImage,
} from "@/lib/preset-files";
import { requireSession } from "@/lib/session";

type Ctx = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, ctx: Ctx) {
  const { error } = await requireSession();
  if (error) return error;
  const { id } = await ctx.params;

  const existing = await prisma.presetBackground.findUnique({ where: { id } });
  if (!existing) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const form = await req.formData();
  const data: { name?: string; imageKey?: string } = {};
  if (form.has("name")) {
    try {
      data.name = parsePresetName(form.get("name"));
    } catch (e) {
      return NextResponse.json(
        { error: e instanceof Error ? e.message : "入力が不正です" },
        { status: 400 }
      );
    }
  }
  const file = form.get("image");
  if (file instanceof File && file.size > 0) {
    try {
      data.imageKey = await savePresetImage("backgrounds", id, file);
    } catch (e) {
      return NextResponse.json(
        { error: e instanceof Error ? e.message : "画像の保存に失敗しました" },
        { status: 400 }
      );
    }
  }

  const updated = await prisma.presetBackground.update({
    where: { id },
    data,
  });
  return NextResponse.json({ background: publicPreset(updated, "backgrounds") });
}

export async function DELETE(_req: Request, ctx: Ctx) {
  const { error } = await requireSession();
  if (error) return error;
  const { id } = await ctx.params;

  const existing = await prisma.presetBackground.findUnique({ where: { id } });
  if (!existing) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const remaining = await prisma.presetBackground.count();
  if (remaining <= 1) {
    return NextResponse.json(
      { error: "背景は最低1つ残してください" },
      { status: 409 }
    );
  }
  const used = await prisma.job.count({ where: { backgroundId: id } });
  if (used > 0) {
    return NextResponse.json(
      { error: "この背景を使っているジョブがあるので消せません" },
      { status: 409 }
    );
  }

  await prisma.presetBackground.delete({ where: { id } });
  await removePresetImage(existing.imageKey);
  return NextResponse.json({ ok: true });
}
