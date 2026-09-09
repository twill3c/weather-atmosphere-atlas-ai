import type { Metadata } from "next";

import MapExplorer from "./MapExplorer";

export const metadata: Metadata = {
  title: "地図 — 日本気象・大気環境アトラス AI",
  description:
    "過去の日付を選び、気象・大気汚染・AI 異常度を日本地図に重ねて見る。天気予報ではありません。",
};

export default function Page() {
  return <MapExplorer />;
}
