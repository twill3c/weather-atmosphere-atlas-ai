"""気象官署に都道府県を割り当てる(SPEC §8)。

気象庁の `prec_no` は予報区であって都道府県ではない(61 種あり 47 と一致しない)。
AI の特徴量は都道府県単位に集約するので、**座標から**都道府県を決める。

国土地理院の逆ジオコーダを使う:
    https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress?lat=..&lon=..
陸上では {"results": {"muniCd": "01217", "lv01Nm": "..."}} を返し、
海上・国外では {} を返す。**これはエラーではなく「陸上でない」という答え**なので
再試行してはならない。muniCd の先頭 2 桁が都道府県コード。

    python scripts/transform/assign_prefectures.py
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from jwaa.domain import filter_domestic                     # noqa: E402
from jwaa.fetch import Fetcher                              # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
MASTER = ROOT / "data" / "processed" / "jma_stations.json"
OUT = ROOT / "data" / "processed" / "station_prefectures.json"

REVERSE = ("https://mreversegeocoder.gsi.go.jp/reverse-geocoder/"
           "LonLatToAddress?lat={lat}&lon={lon}")

PREF_NAMES = [
    "", "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default=str(ROOT / "data" / "cache" / "gsi"))
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    stations = json.loads(MASTER.read_text(encoding="utf-8"))["stations"]
    targets = filter_domestic(
        [s for s in stations if s["kind"] == "s" and s["active"]])
    print(f"対象 {len(targets)} 地点")

    fetcher = Fetcher(pathlib.Path(args.cache), delay_s=args.delay, tries=6)

    def lookup(lat: float, lon: float):
        payload = fetcher.get(REVERSE.format(lat=lat, lon=lon), suffix=".json",
                              validate=lambda b: b.lstrip()[:1] == b"{")
        results = json.loads(payload.decode("utf-8")).get("results")
        if not results or not results.get("muniCd"):
            return None            # 「陸上でない」という答え。再試行しない
        return str(results["muniCd"]).zfill(5), results.get("lv01Nm")

    out: dict[str, dict] = {}
    unresolved = []
    nudged = []
    for s in targets:
        hit = lookup(s["lat"], s["lon"])
        offset_km = 0.0
        if hit is None:
            # 港湾・岬・山頂の観測点は、座標そのものが海上や自治体界の外に落ちる。
            # 同心円状に少しずつ広げて「いちばん近い陸」を探す。手で県名を
            # 決めるのではなく、同じ手続きで再現できる形にする。
            for radius_km in (1.0, 2.0, 3.5, 5.0, 8.0):
                for bearing in range(0, 360, 45):
                    import math
                    rad = math.radians(bearing)
                    dlat = (radius_km / 111.0) * math.cos(rad)
                    dlon = (radius_km / (111.0 * math.cos(math.radians(s["lat"]))
                                         )) * math.sin(rad)
                    hit = lookup(s["lat"] + dlat, s["lon"] + dlon)
                    if hit:
                        offset_km = radius_km
                        break
                if hit:
                    break
        if hit is None:
            unresolved.append(s)
            continue
        muni, muni_name = hit
        code = muni[:2]
        if offset_km:
            nudged.append((s, offset_km, PREF_NAMES[int(code)]))
        out[s["block_no"]] = {
            "block_no": s["block_no"],
            "name": s["name"],
            "pref_code": code,
            "pref_name": PREF_NAMES[int(code)],
            "muni_code": muni,
            "muni_name": muni_name,
            "offset_km": offset_km,
        }

    if nudged:
        print(f"座標が陸に落ちず、近傍を探した地点 {len(nudged)} 件:")
        for s, km, pref in nudged:
            print(f"  {s['block_no']} {s['name']:<8} {km:>4.1f} km 以内 -> {pref}")

    print(f"割り当て {len(out)} / 未解決 {len(unresolved)}")
    for s in unresolved:
        print(f"  未解決: {s['block_no']} {s['name']} ({s['lat']}, {s['lon']})")

    covered = sorted({v["pref_code"] for v in out.values()})
    print(f"現れた都道府県 {len(covered)} / 47")
    missing = [f"{i:02d}" for i in range(1, 48) if f"{i:02d}" not in covered]
    if missing:
        print("  官署の無い県:",
              [f"{c} {PREF_NAMES[int(c)]}" for c in missing])

    OUT.write_text(json.dumps({
        "source": "国土地理院 逆ジオコーダ",
        "note": "気象官署の座標から都道府県を決めた。prec_no は予報区であって県ではない",
        "unresolved": [s["block_no"] for s in unresolved],
        "stations": out,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(" ", fetcher.summary())
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
