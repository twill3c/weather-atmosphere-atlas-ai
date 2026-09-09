import type { Metadata } from "next";

import CompareView from "./CompareView";

export const metadata: Metadata = {
  title: "比較 — 日本気象・大気環境アトラス AI",
  description:
    "2 つの日付を選び、全国平均の差と、AI 表現どうしの類似度を並べて見ます。",
};

export default function Page() {
  return <CompareView />;
}
