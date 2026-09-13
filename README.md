# Japan Weather & Atmosphere Atlas AI

日本気象・大気環境アトラス AI

- 本番: <https://weather-atmosphere-atlas-ai.vercel.app>
- リポジトリ: <https://github.com/twill3c/weather-atmosphere-atlas-ai>
  (手元のディレクトリ名は `japan-weather-atmosphere-atlas`。公開名は app-menu の登録簿の id に合わせた)

日本の過去の気象・温室効果ガス・大気汚染を地図と時系列で重ね、そこに深層学習で
作った表現を添えて「似た日」「異常度」「パターン」を引けるようにする静的 Web アプリ。

> **これは天気予報ではありません。**
> 扱うのは公開されている過去の観測データだけで、独自の予報・警報は出しません
> (気象業務法第 17 条・第 23 条)。

## 何が見られるか

| 画面 | 中身 |
|---|---|
| `/map` | 日付を選んで気象・大気汚染を日本地図に重ねる。再生で日を送れる |
| `/ghg` | 綾里・南鳥島・与那国島の CO₂ / CH₄ を 1987 年から |
| `/patterns` | 日ごとの気象を Autoencoder の表現に直し、2 次元に落として並べる |
| `/compare` | 2 つの日を並べ、要素ごとの差と AI 表現の類似度を出す |
| `/data-policy` | データ源ごとの出典・取得日・加工の有無・再配布の有無・利用条件 |

画面の値は必ず **観測値 / 派生値 / AI 由来** のどれかとして示します。混ぜません。

## データ源(すべて 2026-09-08 以降に実測)

| 源 | 使うもの | 経路 |
|---|---|---|
| 気象庁 | 地上気象観測 日別値、観測地点 | 過去の気象データ検索 `daily_s1.php` |
| 気象庁 | 温室効果ガス 月別値 | 大気・海洋環境観測年報の ZIP |
| 国立環境研究所 | 大気汚染 時間値、測定局 | 環境展望台 ダウンロード |
| 国土地理院 | 背景地図 | 地理院タイル(淡色) |

詳しい実測(件数・欠測・記号の意味・食い違い)は [SPEC.md](SPEC.md) の §2 にあります。

**未文書化の内部 API には依存しません。** 気象庁の `obsdl` は使わず、公開の閲覧画面を
間隔を置いて・キャッシュして・再開可能に読みます。

## 使い方

```bash
git clone <repository>
cd japan-weather-atmosphere-atlas

# Python(取り込みと学習)
python -m venv .venv
.venv/Scripts/Activate.ps1      # Windows。macOS/Linux は source .venv/bin/activate
pip install -r requirements.txt

# Node(画面)
npm install
```

### 取り込み

取得は**キャッシュ済み・再開可能**です。2 回目の実行は外部に要求を出しません。

```bash
python scripts/ingest/jma_stations.py                    # 観測地点マスタ(62 要求)
python scripts/transform/assign_prefectures.py           # 座標から都道府県を決める
python scripts/ingest/jma_ghg.py                         # 温室効果ガス(3 要求)
python scripts/ingest/jma_weather.py --from 2014 --to 2023 --workers 2
python scripts/ingest/nies_air.py --inventory --from 2014 --to 2023   # 量を先に測る
python scripts/ingest/nies_air.py --from 2014 --to 2023
```

気象は 155 地点 × 10 年 × 12 か月 = 18,600 要求で、2 並列で約 3 時間(実測)。
大気汚染は 470 ファイル・約 1,110 MB(実測)。

### 学習と書き出し

```bash
python scripts/ml/build_features.py
python scripts/ml/train_autoencoder.py
python scripts/ml/build_ai_assets.py
python scripts/export/build_web_assets.py
```

### 画面

```bash
npm run dev        # 開発
npm run verify     # 型検査 + テスト + ビルド + 実ブラウザ検品
npm run build      # out/ に静的書き出し
```

## 検査

```bash
pytest -q                  # 取り込み・書式・ゲート表の検査
node harness/smoke.mjs      # 実ブラウザ検品(7 画面 × 4 つの幅)
python harness/text_hygiene.py
```

オラクルは**外部権威**に置いています。どれも我々の解釈を相手が使っていないので循環しません。

- 気象庁が別ページで公表する **CO₂ 年平均**と、配布 ZIP の月別値から自前で出した年平均
  → 91 観測点年すべてが公表の丸め(0.1 ppm)で一致(実測)
- 気象庁が公表する**月ごとの値**と、日別値を自前で集計した月合計・月平均
  → 東京 2023 の 12 か月すべてで一致(実測)
- 観測地点の**四隅**が、独立に知られた極地点(南鳥島・与那国島・稚内)と一致

## 落とし穴(実測で踏んだもの)

SPEC §2 と §11 に全部書いてありますが、とくに効いたのは次の 4 つです。

- 気象庁の `--` は**欠測ではなく「現象がなかった」**。降水量では 0 mm という観測値で、
  欠測として捨てると雨の降らなかった日が全部消える。
- 「官署」は観測所の**種別**であって「日本国内の」という限定を持たない。
  現役官署 156 件には**昭和基地**が入っている。
- 環境展望台の「時間値データ」と題された種別は中身が**集計値**。時系列は別の種別にある。
- 大気汚染の時間値には**センチネルが 3 つ**(9999 欠測 / 9998 未測 / 9997 エラー)あり、
  ファイルは 31 日固定の格子で暦に無い日が 9998 で埋まっている。

## ライセンス

アプリ本体は [MIT](LICENSE)。**外部データには適用されません。**
各データの利用条件は [NOTICE.md](NOTICE.md) と `/data-policy` を参照してください。

出典:気象庁ホームページ ／ 気象庁のデータを加工して作成
国立環境研究所 環境展望台 大気汚染常時監視データファイル ／ 地理院タイル
