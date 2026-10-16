// Copia os dados gerados pelo ETL (frontend/data/rj, data/sp, data/rjm/<slug>) para public/data/,
// de onde o site os busca com fetch. public/data não vai para o git. Roda antes de `next dev` e `next build`.
import { cpSync, existsSync, readdirSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const src = join(root, "data");
const dest = join(root, "public", "data");
rmSync(dest, { recursive: true, force: true });
// restos do esquema antigo (um build por cidade)
for (const old of ["lib/static-data.generated.json", "lib/static-votacoes", "lib/static-vereadores", "public/fotos"]) {
  rmSync(join(root, old), { recursive: true, force: true });
}
let n = 0;
function stage(rel) {
  const dir = join(src, rel);
  if (statSync(dir).isDirectory() && existsSync(join(dir, "static-data.generated.json"))) {
    cpSync(dir, join(dest, rel), { recursive: true });
    n += 1;
  }
}
for (const entry of readdirSync(src)) {
  if (entry === "rjm") {
    for (const slug of readdirSync(join(src, "rjm"))) {
      stage(join("rjm", slug));
    }
  } else if (statSync(join(src, entry)).isDirectory()) {
    stage(entry);
  }
}
console.log(`stage-data: ${n} cidades em public/data`);
