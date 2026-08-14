import fs from "fs";
import path from "path";
import { prisma } from "../src/lib/prisma";

const PERSONA_FILES: Record<string, string> = {
  Sofia: "sofia.jpg",
  Elena: "elena.jpg",
  Mia: "mia.jpg",
};

async function main() {
  const personas = [{ name: "Sofia" }, { name: "Elena" }, { name: "Mia" }];
  const backgrounds = [
    { name: "白大理石" },
    { name: "トラバーチン" },
    { name: "リネン" },
    { name: "黒石" },
  ];
  const tones = [
    { name: "オフィス" },
    { name: "休日" },
    { name: "エレガント" },
    { name: "リラックス" },
  ];

  if ((await prisma.presetPersona.count()) === 0) {
    await prisma.presetPersona.createMany({ data: personas });
  }
  if ((await prisma.presetBackground.count()) === 0) {
    await prisma.presetBackground.createMany({ data: backgrounds });
  }
  if ((await prisma.presetTone.count()) === 0) {
    await prisma.presetTone.createMany({ data: tones });
  }

  const personaDir = path.join(process.cwd(), ".data", "personas");
  const existing = await prisma.presetPersona.findMany();
  for (const p of existing) {
    const file = PERSONA_FILES[p.name];
    if (!file) continue;
    const full = path.join(personaDir, file);
    if (fs.existsSync(full) && p.imageKey !== full) {
      await prisma.presetPersona.update({
        where: { id: p.id },
        data: { imageKey: full },
      });
      console.log(`persona ${p.name} imageKey -> ${full}`);
    }
  }

  console.log("Seeded presets (persona 3 / background 4 / tone 4).");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
