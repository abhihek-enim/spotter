import type { Level } from "../api";

// Risk colours. Checked with a colour-vision validator: every pair of neighbouring levels
// stays distinguishable for red-green colour blindness (worst ΔE 11.3) and normal vision (17.5).
// Colour never works alone: levels are also written as text in the legend, popups and table.
export const LEVELS: { level: Level; key: LevelKey; label: string; color: string }[] = [
  { level: 0, key: "low", label: "Low", color: "#0ca30c" },
  { level: 1, key: "moderate", label: "Moderate", color: "#fab219" },
  { level: 2, key: "high", label: "High", color: "#eb6834" },
  { level: 3, key: "severe", label: "Severe", color: "#a51d1d" },
  { level: 4, key: "no_travel", label: "No Travel", color: "#5b1033" },
];

export type LevelKey = "low" | "moderate" | "high" | "severe" | "no_travel";

export const levelLabel = (level: Level) => LEVELS[level].label;
export const levelColor = (level: Level) => LEVELS[level].color;

/** MapLibre expression: colour by a numeric level stored in a feature property. */
export function levelColorExpression(property: string): unknown[] {
  return ["match", ["get", property], ...LEVELS.flatMap((l) => [l.level, l.color]), "#888888"];
}
