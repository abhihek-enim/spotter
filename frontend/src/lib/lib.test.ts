import { describe, expect, it } from "vitest";
import type { Heatmap, Route } from "../api";
import { nextQuarterHour, slotWindow } from "./format";
import { bandIndex, heatmapGeoJSON, heatmapPaint, VARIABLE_BANDS } from "./heatmap";
import { boundsOf, positionAt } from "./route";

const route = {
  line: [
    [-100, 35],
    [-99.5, 35],
    [-99, 35],
  ],
  line_times_s: [0, 1800, 3600],
} as unknown as Route;

describe("positionAt", () => {
  it("interpolates by time along the line", () => {
    expect(positionAt(route, 900).at).toEqual([-99.75, 35]);
    expect(positionAt(route, 2700).at).toEqual([-99.25, 35]);
  });
  it("stays at the ends before departure and after arrival", () => {
    expect(positionAt(route, -5)).toEqual({ at: [-100, 35], arrived: false });
    expect(positionAt(route, 99_999)).toEqual({ at: [-99, 35], arrived: true });
  });
});

describe("boundsOf", () => {
  it("covers every route point", () => {
    expect(boundsOf([route])).toEqual([
      [-100, 35],
      [-99, 35],
    ]);
  });
});

describe("bandIndex", () => {
  it("uses the risk table's boundary rule", () => {
    const wind = VARIABLE_BANDS.wind.edges;
    expect(bandIndex(9.9, wind)).toBe(0);
    expect(bandIndex(25, wind)).toBe(2);
    expect(bandIndex(55, wind)).toBe(5);
    const rain = VARIABLE_BANDS.rain.edges;
    expect(bandIndex(0.25, rain, true)).toBe(3);
    expect(bandIndex(1.0, rain, true)).toBe(4); // exactly 1.00 is not "more than 1.00"
    expect(bandIndex(1.01, rain, true)).toBe(5);
  });
});

describe("heatmap", () => {
  const h: Heatmap = {
    step_deg: 0.2,
    slot0_start: "2026-11-04T14:00:00Z",
    slots: 2,
    cells: [[-100, 35]],
    risk: [[0, 3]],
    wind: [[5, 47]],
    rain: [[0, 0.3]],
    snow: [[0, 0]],
  };

  it("builds one square per cell with every hour as a property", () => {
    const fc = heatmapGeoJSON(h);
    expect(fc.features).toHaveLength(1);
    const f = fc.features[0];
    expect(f.properties).toMatchObject({ r0: 0, r1: 3, w0: 0, w1: 4, p1: 3 });
    expect(f.geometry.coordinates[0][0]).toEqual([-100.1, 34.9]);
  });

  it("switching hours only changes the property the paint reads", () => {
    expect(JSON.stringify(heatmapPaint("risk", 7))).toContain('"r7"');
    expect(JSON.stringify(heatmapPaint("wind", 12))).toContain('"w12"');
  });
});

describe("time helpers", () => {
  it("rounds up to the next quarter hour", () => {
    expect(nextQuarterHour(new Date(2026, 10, 4, 9, 7, 30)).getMinutes()).toBe(15);
    expect(nextQuarterHour(new Date(2026, 10, 4, 9, 59)).getHours()).toBe(10);
  });
  it("gives the hour window of a slot", () => {
    const { start, end } = slotWindow("2026-11-04T14:00:00Z", 3);
    expect(start.toISOString()).toBe("2026-11-04T17:00:00.000Z");
    expect(end.toISOString()).toBe("2026-11-04T18:00:00.000Z");
  });
});
