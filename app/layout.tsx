import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "日本気象・大気環境アトラス AI",
  description:
    "気象庁の地上気象観測・温室効果ガスと、国立環境研究所の大気汚染常時監視を地図と時系列で重ね、" +
    "深層学習の表現で似た日・異常度・パターンを引く静的アトラス。天気予報は行いません。",
};

/** フリート共通フッタの行き先(koho-lens が正本)。 */
const FOOTER = {
  license:
    "https://github.com/twill3c/weather-atmosphere-atlas-ai/blob/main/LICENSE",
  repository: "https://github.com/twill3c/weather-atmosphere-atlas-ai",
  // 解説アーティファクト 2 本(loop_002 で発行。既定は非公開なので共有設定が要る)
  guide: "https://claude.ai/code/artifact/24b377ac-3a54-44e8-b0f9-e9276b12a463",
  blueprint: "https://claude.ai/code/artifact/944f0c2d-106f-4b34-8692-293b90a56d2c",
  appMenu: "https://app-menu-amber.vercel.app/",
};

const NAV = [
  { href: "/map/", label: "地図" },
  { href: "/ghg/", label: "温室効果ガス" },
  { href: "/patterns/", label: "パターン" },
  { href: "/compare/", label: "比較" },
  { href: "/about/", label: "このアトラスについて" },
  { href: "/data-policy/", label: "データの出典" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>
        <nav className="nav" aria-label="主要">
          <a className="nav__brand" href="/">
            日本気象・大気環境アトラス AI
          </a>
          {NAV.map((item) => (
            <a key={item.href} href={item.href}>
              {item.label}
            </a>
          ))}
        </nav>
        {children}
        <footer className="site-footer">
          <div className="site-footer__inner">
            <a href={FOOTER.license}>MIT License</a>
            <span className="site-footer__copy">© 2026 坂田哲朗</span>
            <span className="fsep">・</span>
            <a href={FOOTER.repository}>GitHub</a>
            <span className="fsep">・</span>
            <a href={FOOTER.guide}>アトラスの歩き方</a>
            <span className="fsep">・</span>
            <a href={FOOTER.blueprint}>アトラスの設計図</a>
            <span className="fsep">・</span>
            <a href={FOOTER.appMenu}>App Menu</a>
          </div>
        </footer>
      </body>
    </html>
  );
}
