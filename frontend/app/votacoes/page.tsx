import type { Metadata } from "next";
import { VotacoesPage } from "@/components/Municipio";

export const metadata: Metadata = { title: "Votações" };

export default function Route() {
  return <VotacoesPage />;
}
