import type { Metadata } from "next";
import { PartidosPage } from "@/components/Municipio";

export const metadata: Metadata = { title: "Partidos" };

export default function Route() {
  return <PartidosPage />;
}
