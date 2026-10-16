// O site mora em g0v.tomoyo.systems/vereadores. Um só build serve todas as cidades: Rio na raiz,
// São Paulo em /sp/, os municípios do Estado do Rio em /rj/<slug>/ (lib/uf.ts).
// NEXT_PUBLIC_BASE_PATH="" serve na raiz (testes).
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "/vereadores";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  basePath,
  assetPrefix: basePath || undefined,
  trailingSlash: true,
  images: {
    unoptimized: true
  },
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath
  }
};

module.exports = nextConfig;
