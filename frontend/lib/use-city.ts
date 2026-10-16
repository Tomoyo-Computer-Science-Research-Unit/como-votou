"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { currentCity, getCore, subscribeCore, type Core } from "@/lib/static-api";
import { splitPath, type Cidade } from "@/lib/uf";

/** Cidade e tela da página atual (só em componentes cliente). */
export function useCity(): { city: Cidade; screen: string } {
  return splitPath(usePathname() ?? "/");
}

/** O núcleo instalado pelo DataGate, ou null enquanto carrega (para quem fica fora do DataGate). */
export function useLoadedCore(): Core | null {
  return useSyncExternalStore(
    subscribeCore,
    () => (currentCity() ? getCore() : null),
    () => null
  );
}
