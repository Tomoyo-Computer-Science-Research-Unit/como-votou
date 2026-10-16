"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CIDADES, cityRoute, type Cidade } from "@/lib/uf";
import { useCity } from "@/lib/use-city";

function fold(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/**
 * Seletor de cidade com busca, no cabeçalho: um campo com a cara dos seletores de ano; ao focar,
 * abre a lista das cidades, filtrada pelo que se digita. Enter abre a mesma tela na cidade
 * escolhida; Esc fecha.
 */
export function CitySearch() {
  const router = useRouter();
  const { city, screen } = useCity();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);

  const options = useMemo(() => {
    const q = fold(query.trim());
    return q ? CIDADES.filter((item) => fold(item.nome).includes(q)) : CIDADES;
  }, [query]);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onDown(event: MouseEvent) {
      if (box.current && !box.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(target: Cidade | undefined) {
    setOpen(false);
    setQuery("");
    if (target && target.key !== city.key) {
      router.push(cityRoute(target, screen));
    }
  }

  return (
    <div ref={box} className="citysearch">
      <input
        className="yearselect citysearch__input"
        role="combobox"
        aria-label="Cidade"
        aria-expanded={open}
        aria-controls="citysearch-list"
        aria-autocomplete="list"
        spellCheck={false}
        autoComplete="off"
        value={open ? query : city.nome}
        placeholder={city.nome}
        onFocus={() => {
          setOpen(true);
          setQuery("");
          setActive(Math.max(0, CIDADES.findIndex((item) => item.key === city.key)));
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((index) => Math.min(options.length - 1, index + 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((index) => Math.max(0, index - 1));
          } else if (event.key === "Enter") {
            event.preventDefault();
            choose(options[active]);
            event.currentTarget.blur();
          } else if (event.key === "Escape") {
            setOpen(false);
            setQuery("");
            event.currentTarget.blur();
          }
        }}
      />
      {open ? (
        <ul id="citysearch-list" ref={list} role="listbox" aria-label="Cidades" className="citysearch__list">
          {options.length === 0 ? <li className="citysearch__empty">nenhuma cidade</li> : null}
          {options.map((item, index) => (
            <li
              key={item.key}
              role="option"
              data-index={index}
              aria-selected={index === active}
              aria-current={item.key === city.key ? "true" : undefined}
              onMouseDown={(event) => {
                event.preventDefault();
                choose(item);
              }}
              onMouseEnter={() => setActive(index)}
            >
              <span>{item.nome}</span>
              <span className="num">{item.kind === "capital" ? "capital" : ""}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
