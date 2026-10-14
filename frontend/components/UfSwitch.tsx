"use client";

import { usePathname } from "next/navigation";
import { CIDADES, UF, cityHref } from "@/lib/uf";

/** Seletor de cidade no cabeçalho. Cada cidade é um build próprio: trocar navega para a mesma tela na outra. */
export function UfSwitch() {
  const pathname = usePathname();
  return (
    <select
      className="yearselect"
      aria-label="Cidade"
      value={UF}
      onChange={(event) => {
        const cidade = CIDADES.find((item) => item.uf === event.target.value);
        if (cidade) {
          window.location.href = cityHref(cidade, pathname);
        }
      }}
    >
      {CIDADES.map((cidade) => (
        <option key={cidade.uf} value={cidade.uf}>
          {cidade.nome}
        </option>
      ))}
    </select>
  );
}
