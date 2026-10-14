// O site mora em g0v.tomoyo.systems/vereadores: a cidade raiz (data/cities.json, root=true) em
// /vereadores e as demais em /vereadores/<slug>. NEXT_PUBLIC_UF escolhe a cidade do build;
// NEXT_PUBLIC_BASE_PATH="" serve na raiz.
const { cities } = require("./data/cities.json");

const root = cities.find((item) => item.root) || cities[0];
const uf = (process.env.NEXT_PUBLIC_UF || root.uf).toUpperCase();
const city = cities.find((item) => item.uf.toUpperCase() === uf) || root;
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? (city.root ? "/vereadores" : `/vereadores/${city.slug}`);

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
    NEXT_PUBLIC_BASE_PATH: basePath,
    NEXT_PUBLIC_UF: city.uf.toUpperCase()
  }
};

module.exports = nextConfig;
