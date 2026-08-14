import fs from "fs/promises";
import path from "path";
import { NextResponse } from "next/server";
import { SLOT_KEYS, type SlotKey } from "@ti-amo/shared";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { jobDir } from "@/lib/dummy-assets";

type Ctx = { params: Promise<{ id: string; slot: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { error } = await requireSession();
  if (error) return error;

  const { id, slot } = await ctx.params;
  if (!(SLOT_KEYS as readonly string[]).includes(slot)) {
    return NextResponse.json({ error: "Unknown slot" }, { status: 400 });
  }

  const asset = await prisma.jobAsset.findFirst({
    where: { jobId: id, slotKey: slot, kind: "preview" },
  });
  if (!asset) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const root = path.resolve(jobDir(id));
  const filePath = path.resolve(asset.storageKey);
  const rel = path.relative(root, filePath);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  try {
    const buf = await fs.readFile(filePath);
    return new NextResponse(buf, {
      headers: {
        "Content-Type": "image/jpeg",
        "Cache-Control": "private, no-store, max-age=0, must-revalidate",
      },
    });
  } catch {
    return NextResponse.json({ error: "File missing" }, { status: 404 });
  }
}
