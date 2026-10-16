import { defineConfig, devices } from "@playwright/test";

// Um só build serve todas as cidades: Rio na raiz, São Paulo em /sp/, os municípios do Estado do
// Rio em /rj/<slug>/. Cada projeto testa uma cidade; metadata.prefix diz onde ela mora e
// metadata.nivel o que ela publica (0 = só vereadores, pelo TSE; 3 = votos nominais).
const desktop = { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } };
// Palco mínimo do site (1280×720): abaixo disso a página rola, o layout não cede.
const minimo = { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 720 } };

const CIDADES = [
  { slug: "rio", prefix: "", nome: "Rio de Janeiro", nivel: 3 },
  { slug: "sp", prefix: "/sp", nome: "São Paulo", nivel: 3 },
  { slug: "niteroi", prefix: "/rj/niteroi", nome: "Niterói", nivel: 0 },
  { slug: "macuco", prefix: "/rj/macuco", nome: "Macuco", nivel: 0 },
  { slug: "petropolis", prefix: "/rj/petropolis", nome: "Petrópolis", nivel: 3 }
];

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  expect: {
    timeout: 10_000
  },
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure"
  },
  webServer: {
    // Os testes rodam na raiz; o deploy em g0v.tomoyo.systems usa a base /vereadores.
    command: "NEXT_PUBLIC_BASE_PATH= npm run build && npx serve out -l 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 600_000
  },
  projects: CIDADES.flatMap((city) => [
    { name: `${city.slug}-desktop`, use: desktop, metadata: city },
    { name: `${city.slug}-min`, use: minimo, metadata: city }
  ])
});
