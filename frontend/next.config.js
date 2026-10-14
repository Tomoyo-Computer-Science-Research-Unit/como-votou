// O site mora em g0v.tomoyo.systems/vereadores. NEXT_PUBLIC_BASE_PATH="" serve na raiz.
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
