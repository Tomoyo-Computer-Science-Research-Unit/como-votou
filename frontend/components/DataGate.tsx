"use client";

import { Fragment, useEffect, useState, type ReactNode } from "react";
import { EmptyState } from "@/components/ui";
import { loadCore, setCore, type Core } from "@/lib/static-api";
import { useCity } from "@/lib/use-city";

/**
 * Busca o núcleo de dados da cidade da página e só então renderiza a tela. As telas leem o núcleo
 * pelos getters de lib/static-api, de forma síncrona; trocar de cidade remonta a tela (key).
 */
export function DataGate({ children }: { children: ReactNode }) {
  const { city } = useCity();
  const [loaded, setLoaded] = useState<{ key: string; core: Core } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setError(null);
    loadCore(city)
      .then((core) => {
        if (alive) {
          setLoaded({ key: city.key, core });
        }
      })
      .catch((reason: unknown) => {
        if (alive) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => {
      alive = false;
    };
  }, [city]);

  if (!loaded || loaded.key !== city.key) {
    return <EmptyState>{error ? `DADOS INDISPONÍVEIS · ${error}` : "CARREGANDO"}</EmptyState>;
  }
  setCore(city, loaded.core);
  return <Fragment key={city.key}>{children}</Fragment>;
}
