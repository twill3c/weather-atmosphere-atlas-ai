# テストフィクスチャの出所

すべて 2026-09-08 に取得。加工していない配布形のまま置く(HC-139)。

## 気象庁(公共データ利用規約 第1.0版)

出典: 気象庁ホームページ

| ファイル | 取得元 |
|---|---|
| `jma/daily_tokyo_2023_{01..12}.html` | `https://www.data.jma.go.jp/stats/etrn/view/daily_s1.php?prec_no=44&block_no=47662&year=2023&month={M}&day=&view=` |
| `jma/monthly_tokyo_2023.html` | `https://www.data.jma.go.jp/stats/etrn/view/monthly_s1.php?prec_no=44&block_no=47662&year=2023&month=&day=&view=` |
| `jma/pref44.html` | `https://www.data.jma.go.jp/stats/etrn/select/prefecture.php?prec_no=44&block_no=&year=&month=&day=&view=` |
| `jma/co2_yearave.html` | `https://www.data.jma.go.jp/ghg/kanshi/obs/co2_yearave.html` |
| `jma/remark.html` | `https://www.data.jma.go.jp/stats/data/mdrr/man/remark.html` |
| `jma/ghg_monthly/{ry,mi,yo}_m.{co2,ch4}` | `https://www.data.jma.go.jp/env/data/report/data/download/atm_bg/{co2,ch4}.zip` 内の `monthly/` |
| `jma/ghg_monthly/readme_{co2,ch4}.txt` | 同 ZIP 内の `readme_j.txt`(書式定義の出所) |

## 国立環境研究所

**同梱しない。** 環境展望台の掲載情報の著作権は国立環境研究所に帰属するため、
生ファイルはリポジトリに置かない(SPEC §2.5 / N-04)。
NIES に関わるテストは合成フィクスチャで書き、取得済みキャッシュ
(`data/cache/nies/`)が在るときだけ `integration` マーカーの追加検査が走る。
