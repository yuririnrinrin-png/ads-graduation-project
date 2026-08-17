import fs from "fs/promises";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { resolvePresetFile } from "@/lib/preset-files";
import { requireSession } from "@/lib/session";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { error } = await requireSession();
  if (error) return error;
  const { id } = await ctx.params;

  const row = await prisma.presetPersona.findUnique({ where: { id } });
  if (!row?.imageKey) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  if (row.imageKey.startsWith("http://") || row.imageKey.startsWith("https://")) {
    return NextResponse.redirect(row.imageKey);
  }
  const filePath = resolvePresetFile(row.imageKey);
  if (!filePath) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }
  try {
    const buf = await fs.readFile(filePath);
    return new NextResponse(buf, {
      headers: {
        "Content-Type": "image/jpeg",
        "Cache-Control": "private, max-age=60",
      },
    });
  } catch {
    return NextResponse.json({ error: "File missing" }, { status: 404 });
  }
}
