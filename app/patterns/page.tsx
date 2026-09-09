import type { Metadata } from "next";

import PatternMap from "./PatternMap";

export const metadata: Metadata = {
  title: "パターン — 日本気象・大気環境アトラス AI",
  description:
    "日ごとの全国の気象を Autoencoder で表現に直し、2 次元に落として並べた地図。似た日が近くに来ます。",
};

export default function Page() {
  return <PatternMap />;
}
