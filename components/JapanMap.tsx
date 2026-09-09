"use client";

/** 地理院タイルを背景にした日本地図(SPEC F-01 / F-02 / §8)。
 *
 * 出典「地理院タイル」は地図上に常時表示する(§10・国土地理院コンテンツ利用規約)。
 * 観測点の無い場所に値を描かない —— 既定は実測点のみの表示で、
 * 補間は行わない(§20 / §6)。
 */
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";

import { colorFor, type LayerDef } from "@/lib/layers";
import type { StationBase } from "@/lib/types";

export interface MapPoint extends StationBase {
  value: number | null;
}

const GSI_ATTRIBUTION =
  '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noreferrer">地理院タイル</a>';

const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    gsi: {
      type: "raster",
      tiles: ["https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png"],
      tileSize: 256,
      minzoom: 2,
      maxzoom: 18,
      attribution: GSI_ATTRIBUTION,
    },
  },
  layers: [{ id: "gsi", type: "raster", source: "gsi" }],
};

export default function JapanMap({
  points,
  layer,
  selectedId,
  onSelect,
}: {
  points: MapPoint[];
  layer: LayerDef;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  // クリックの受け手は再描画で作り直されるので、掴み置きせず ref から引く(HC-080)
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!container.current || map.current) return;
    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [137.5, 37.5],
      zoom: 4.2,
      minZoom: 3,
      maxZoom: 12,
      attributionControl: false,
    });
    m.addControl(
      new maplibregl.AttributionControl({ compact: false, customAttribution: [] }),
      "bottom-right",
    );
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("stations", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "stations-circle",
        type: "circle",
        source: "stations",
        paint: {
          "circle-radius": [
            "interpolate", ["linear"], ["zoom"],
            4, ["case", ["get", "selected"], 7, 4.5],
            9, ["case", ["get", "selected"], 13, 9],
          ],
          "circle-color": ["get", "color"],
          "circle-opacity": 0.92,
          "circle-stroke-width": ["case", ["get", "selected"], 2.5, 0.8],
          "circle-stroke-color": ["case", ["get", "selected"], "#16202b", "#ffffff"],
        },
      });
      // 欠測は色を与えず、輪郭だけの点にする(0 と見せない — SPEC F-15)
      m.addLayer({
        id: "stations-missing",
        type: "circle",
        source: "stations",
        filter: ["==", ["get", "missing"], true],
        paint: {
          "circle-radius": 3,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-width": 1,
          "circle-stroke-color": "#9aa7b5",
        },
      });
      m.on("click", "stations-circle", (e) => {
        const f = e.features?.[0];
        if (f?.properties?.id) onSelectRef.current(String(f.properties.id));
      });
      m.on("mouseenter", "stations-circle", () => {
        m.getCanvas().style.cursor = "pointer";
      });
      m.on("mouseleave", "stations-circle", () => {
        m.getCanvas().style.cursor = "";
      });
      ready.current = true;
      m.fire("jwaa:ready");
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
      ready.current = false;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      const src = m.getSource("stations") as maplibregl.GeoJSONSource | undefined;
      if (!src) return;
      src.setData({
        type: "FeatureCollection",
        features: points.map((p) => ({
          type: "Feature" as const,
          geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
          properties: {
            id: p.id,
            name: p.name,
            value: p.value,
            missing: p.value === null,
            selected: p.id === selectedId,
            color: p.value === null ? "rgba(0,0,0,0)" : colorFor(layer, p.value),
          },
        })),
      });
    };
    if (ready.current) apply();
    else m.once("jwaa:ready", apply);
  }, [points, layer, selectedId]);

  return (
    <div
      ref={container}
      className="map-canvas"
      role="application"
      aria-label={`${layer.label}の地図`}
      data-testid="japan-map"
      data-points={points.length}
      data-missing={points.filter((p) => p.value === null).length}
    />
  );
}
