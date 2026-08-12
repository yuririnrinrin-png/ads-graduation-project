import fs from "fs/promises";
import path from "path";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { requireSession } from "@/lib/session";
import { jobDir } from "@/lib/queue";

type Ctx = { params: Promise<{ id: string }> };

/** Serves the main product cutout (transparent PNG) used to render a
 * draggable jewel overlay on top of the scene image. */
export async function GET(_req: Request, ctx: Ctx) {
  const { error } = await requireSession();
  if (error) return error;

  const { id } = await ctx.params;
  const job = await prisma.job.findUnique({ where: { id } });
  if (!job) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const asset = await prisma.jobAsset.findFirst({
    where: { jobId: id, slotKey: `cutout_${job.mainIndex}`, kind: "cutout" },
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
        "Content-Type": "image/png",
        "Cache-Control": "private, max-age=60",
      },
    });
  } catch {
    return NextResponse.json({ error: "File missing" }, { status: 404 });
  }
}
