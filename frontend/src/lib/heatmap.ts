import type { FeatureCollection, Polygon } from "geojson";
import type { Heatmap } from "../api";
import { levelColorExpression } from "./risk";

export type HeatLayer = "risk" | "wind" | "rain" | "snow";

/**
 * Bands for the wind / rain / snow views. They use the brief's thresholds, so a cell's colour
 * band lines up with the risk table. Band 0 means calm / dry and is drawn almost transparent.
 * (Display only: all risk decisions are made on the server.)
 */
export const VARIABLE_BANDS: Record<Exclude<HeatLayer, "risk">, { unit: string; edges: number[]; labels: string[] }> = {
  wind: { unit: "mph", edges: [10, 25, 35, 45, 55], labels: ["10–24", "25–34", "35–44", "45–54", "55+"] },
  rain: { unit: "in/hr", edges: [0.01, 0.1, 0.25, 0.5, 1.0], labels: ["< 0.10", "0.10–0.24", "0.25–0.49", "0.50–1.00", "> 1.00"] },
  snow: { unit: "in/hr", edges: [0.05, 0.5, 1.0, 2.0, 3.0], labels: ["< 0.5", "0.5–0.9", "1.0–1.9", "2.0–3.0", "> 3.0"] },
};

// One-hue blue ramp (light -> dark) for magnitude.
export const BAND_COLORS = ["#b7d3f6", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"];

/** Index 0..5 of the band a value falls in. Lower edges count (same rule as the risk table),
 *  except the top band for rain and snow, which is "more than" like the No Travel column. */
export function bandIndex(value: number, edges: number[], strictTop = false): number {
  let band = 0;
  edges.forEach((edge, i) => {
    const isTop = i === edges.length - 1;
    if (isTop && strictTop ? value > edge : value >= edge) band = i + 1;
  });
  return band;
}

/**
 * Build the heatmap once per trip. Every cell carries its value for all 49 hours as
 * properties (r0..r48 risk, w/p/s for wind/rain/snow bands), so moving the slider only
 * changes which property the layer reads: no new data is sent to the map.
 */
export function heatmapGeoJSON(h: Heatmap): FeatureCollection<Polygon> {
  const half = h.step_deg / 2;
  return {
    type: "FeatureCollection",
    features: h.cells.map(([lon, lat], i) => {
      const properties: Record<string, number> = { i };
      for (let k = 0; k < h.slots; k++) {
        properties[`r${k}`] = h.risk[i][k];
        properties[`w${k}`] = bandIndex(h.wind[i][k], VARIABLE_BANDS.wind.edges);
        properties[`p${k}`] = bandIndex(h.rain[i][k], VARIABLE_BANDS.rain.edges, true);
        properties[`s${k}`] = bandIndex(h.snow[i][k], VARIABLE_BANDS.snow.edges, true);
      }
      return {
        type: "Feature",
        id: i,
        properties,
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [lon - half, lat - half],
              [lon + half, lat - half],
              [lon + half, lat + half],
              [lon - half, lat + half],
              [lon - half, lat - half],
            ],
          ],
        },
      };
    }),
  };
}

const PREFIX: Record<HeatLayer, string> = { risk: "r", wind: "w", rain: "p", snow: "s" };

/** Paint for the heatmap fill layer at a given hour. Cheap to rebuild on every slider move. */
export function heatmapPaint(layer: HeatLayer, hour: number) {
  const property = `${PREFIX[layer]}${hour}`;
  if (layer === "risk") {
    return {
      "fill-color": levelColorExpression(property),
      // Low risk is a faint wash so the corridor stays visible; higher levels stand out.
      "fill-opacity": ["match", ["get", property], 0, 0.1, 1, 0.38, 2, 0.45, 3, 0.52, 0.6],
    };
  }
  return {
    "fill-color": ["match", ["get", property], ...BAND_COLORS.flatMap((c, i) => [i + 1, c]), "#ffffff"],
    "fill-opacity": ["match", ["get", property], 0, 0.06, 0.55],
  };
}
