import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { parsePresetName, publicPreset, savePresetImage } from "@/lib/preset-files";
import { requireSession } from "@/lib/session";

export async function POST(req: Request) {
  const { error } = await requireSession();
  if (error) return error;

  const form = await req.formData();
  let name: string;
  try {
    name = parsePresetName(form.get("name"));
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "入力が不正です" },
      { status: 400 }
    );
  }

  const created = await prisma.presetBackground.create({ data: { name } });
  const file = form.get("image");
  if (file instanceof File && file.size > 0) {
    try {
      const imageKey = await savePresetImage("backgrounds", created.id, file);
      const updated = await prisma.presetBackground.update({
        where: { id: created.id },
        data: { imageKey },
      });
      return NextResponse.json({ background: publicPreset(updated, "backgrounds") });
    } catch (e) {
      await prisma.presetBackground.delete({ where: { id: created.id } });
      return NextResponse.json(
        { error: e instanceof Error ? e.message : "画像の保存に失敗しました" },
        { status: 400 }
      );
    }
  }

  return NextResponse.json({ background: publicPreset(created, "backgrounds") });
}
