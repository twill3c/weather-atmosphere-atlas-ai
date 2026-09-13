import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "このアトラスについて — 日本気象・大気環境アトラス AI",
  description:
    "何を測り、何を測っていないか。データの読み方と、AI が出す値の意味。",
};

export default function Page() {
  return (
    <main className="wrap">
      <h1>このアトラスについて</h1>
      <p className="lede">
        日本の過去の空を、地図と時系列で辿るための道具です。
        予報はしません。ここにあるのは観測されたものと、そこから導いたものだけです。
      </p>

      <h2>3 つの区分</h2>
      <p>
        画面に出る値は、必ず次のどれかとして示します。混ぜません。
      </p>
      <ul>
        <li>
          <span className="badge badge--observed">観測値</span>{" "}
          気象庁・国立環境研究所が公表した測定値そのもの。
        </li>
        <li>
          <span className="badge badge--derived">派生値</span>{" "}
          平均・移動平均・平年差など、観測から素直に計算したもの。
        </li>
        <li>
          <span className="badge badge--ai">AI 由来</span>{" "}
          Autoencoder の表現から出した異常度・類似度・クラスタ。
          <strong>観測された量ではありません。</strong>
        </li>
      </ul>

      <h2>「データなし」を 0 と書かない</h2>
      <p>
        観測されなかった日と、観測して 0 だった日は違います。地図では、値のある地点を
        色の付いた丸で、データのない地点を<strong>輪郭だけの丸</strong>で描き分けます。
      </p>
      <p className="small muted">
        気象庁の値欄には記号があります。<code>--</code> は「その現象がなかった」で、
        降水量なら 0 mm という<strong>観測値</strong>です(欠測ではありません)。
        <code>0.0</code> は「あったが 0.5 mm に満たない」。
        <code>×</code> <code>///</code> と空欄が欠測です。
        <code>)</code> は準正常値(資料が 8 割はある)、<code>]</code> は資料不足値で、
        後者は値を採りません。
      </p>

      <h2>補間しない</h2>
      <p>
        観測地点は日本全国に均等には無く、とくに温室効果ガスは 3 地点しかありません。
        観測点の無い場所の値を作って「観測値」のように見せることはしません。
      </p>

      <h2>AI が出す値の意味</h2>
      <p>
        日ごとの全国の気象を 1 本のベクトルにまとめ、Autoencoder に通します。
        元に戻したときの誤差が大きい日ほど「学習した並びから外れている」ことになり、
        その順位を 0〜100 で表したのが<strong>異常度</strong>です。
      </p>
      <ul>
        <li>異常度は<strong>災害の危険度ではありません</strong>。</li>
        <li>
          変数ごとの内訳は「再構成誤差への寄与」であって、
          <strong>原因の説明ではありません</strong>。
        </li>
        <li>
          似た日は、季節だけで似てしまうのを避けるため、既定では同じ時期どうしで比べます。
        </li>
        <li>クラスタの番号はモデルが付けたもので、説明のラベルは人が後から付けています。</li>
      </ul>

      <h2>収録の範囲</h2>
      <p className="small muted">
        気象は国内の現役気象官署 155 地点の日別値。大気汚染は全国の測定局の時間値を
        日別に集約したもので、時間値が公開されているのは 2009 年度以降です。
        温室効果ガスは綾里・南鳥島・与那国島の月別値で、二酸化炭素は 1987 年から。
      </p>

      <h2>作り方</h2>
      <p className="small muted">
        取得・正規化は Python、表現の学習は PyTorch、画面は Next.js と MapLibre GL JS。
        サーバ側の処理は持たず、静的ファイルだけを配っています。
        設計と実測の記録は<a href="https://github.com/twill3c/weather-atmosphere-atlas-ai">リポジトリ</a>にあります。
      </p>
    </main>
  );
}
