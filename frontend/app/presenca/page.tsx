import type { Metadata } from "next";
import { PresencaPage } from "@/components/Municipio";

export const metadata: Metadata = { title: "Presença" };

export default function Route() {
  return <PresencaPage />;
}
