# Data Attribution

本アプリが利用する外部データの出典と条件。実際の公開時には各提供元の最新の
利用条件に合わせて更新する(最終確認 2026-09-08)。

アプリ本体のライセンスは MIT(`LICENSE`)。**MIT は外部データには適用されない。**

---

## 気象庁 (Japan Meteorological Agency)

- 地上気象観測 日別値・月別値、観測地点情報
  <https://www.data.jma.go.jp/stats/etrn/>
- 大気・海洋環境観測年報 温室効果ガス観測値(綾里・南鳥島・与那国島)
  <https://www.data.jma.go.jp/env/data/report/data/download/atm_bg_j.html>
- 二酸化炭素濃度の年平均値
  <https://www.data.jma.go.jp/ghg/kanshi/obs/co2_yearave.html>

気象庁ホームページのコンテンツは、権利表記の記載がない限り
**公共データ利用規約(第 1.0 版)**に準拠した条件で利用できる。

> 出典:気象庁ホームページ

本アプリは上記データを**加工して**利用している(単位の正規化・日別値の集計・
平年偏差の算出・機械学習による表現の作成)。

> 気象庁のデータを加工して作成

気象業務法第 17 条(予報業務の許可)および第 23 条(警報の制限)の定めにより、
本アプリは独自の予報・警報を発表しない(SPEC §1 / §3.2)。

---

## 国立環境研究所 (National Institute for Environmental Studies)

- 環境展望台 大気汚染常時監視データ
  <https://tenbou.nies.go.jp/download/>

> 国立環境研究所 環境展望台
> 大気汚染常時監視データファイル

環境展望台に掲載されている情報の著作権は国立環境研究所に帰属する。
本アプリは**生ファイルを再配布しない**。公開するのは、時間値から算出した
日別値・地域別の集計といった派生値のみで、クレジットを添える。

---

## 国土地理院 (Geospatial Information Authority of Japan)

- 地理院タイル
  <https://maps.gsi.go.jp/development/ichiran.html>
- コンテンツ利用規約
  <https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html>

> 地理院タイル

地図表示中は常に出典を表示する。

---

## 本アプリの位置づけ

本アプリは公開されている観測データと、そこから機械学習で導いた表現を可視化する
教育・研究支援・探索的分析のための道具である。**天気予報サービスではない。**
画面上の値は、観測値(OBSERVED)・派生値(DERIVED)・AI 由来(AI_DERIVED)を
区別して表示する。
