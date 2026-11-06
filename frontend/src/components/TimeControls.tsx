import { useEffect } from "react";
import type { TripResult } from "../api";
import { formatClock } from "../lib/format";
import { BAND_COLORS, VARIABLE_BANDS, type HeatLayer } from "../lib/heatmap";
import { LEVELS } from "../lib/risk";
import { positionAt } from "../lib/route";

interface Props {
  result: TripResult;
  heatmapState: "loading" | "failed" | "ready";
  onRetryHeatmap: () => void;
  selectedId: string;
  hour: number;
  onHour: (hour: number) => void;
  layer: HeatLayer;
  onLayer: (layer: HeatLayer) => void;
  playing: boolean;
  onPlaying: (playing: boolean) => void;
}

const SLIDER_HOURS = 48; // the brief's 0-48 h forecast slider

const LAYERS: { id: HeatLayer; label: string }[] = [
  { id: "risk", label: "Risk" },
  { id: "wind", label: "Wind" },
  { id: "rain", label: "Rain" },
  { id: "snow", label: "Snow" },
];

/** Forecast slider (0–48 h after departure), play button, heatmap layer switch and legend. */
export function TimeControls({
  result,
  heatmapState,
  onRetryHeatmap,
  selectedId,
  hour,
  onHour,
  layer,
  onLayer,
  playing,
  onPlaying,
}: Props) {
  const max = SLIDER_HOURS;

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => onHour(hour >= max ? 0 : hour + 1), 450);
    return () => window.clearInterval(timer);
  }, [playing, hour, max, onHour]);

  const departure = new Date(result.trip.departure);
  const moment = new Date(departure.getTime() + hour * 3_600_000);
  const route = result.routes.find((r) => r.id === selectedId);
  const truck = route ? positionAt(route, hour * 3600) : null;

  return (
    <div className="time-controls">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="play-button"
          onClick={() => onPlaying(!playing)}
          aria-label={playing ? "Pause forecast animation" : "Play forecast animation"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2 text-sm">
            <label htmlFor="hour" className="font-semibold">
              Departure +{hour} h <span className="font-normal text-[var(--text-secondary)]">· {formatClock(moment)}</span>
            </label>
            <span className="truncate text-xs text-[var(--text-secondary)]">
              {truck ? (truck.arrived ? `Route ${selectedId} has arrived` : `🚚 Route ${selectedId} on the road`) : ""}
            </span>
          </div>
          <input
            id="hour"
            type="range"
            min={0}
            max={max}
            step={1}
            value={hour}
            onChange={(e) => onHour(Number(e.target.value))}
            className="w-full"
            aria-valuetext={`${hour} hours after departure`}
          />
        </div>
      </div>

      <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
        <div className="segmented small" role="radiogroup" aria-label="Heatmap shows">
          {LAYERS.map((l) => (
            <label key={l.id} className={layer === l.id ? "segment selected" : "segment"}>
              <input type="radio" name="heat-layer" className="sr-only" checked={layer === l.id} onChange={() => onLayer(l.id)} />
              {l.label}
            </label>
          ))}
        </div>
        {heatmapState === "ready" ? (
          <Legend layer={layer} />
        ) : heatmapState === "loading" ? (
          <span className="text-xs text-[var(--text-secondary)]" role="status">
            Loading the 48-hour weather grid…
          </span>
        ) : (
          <span className="flex items-center gap-2 text-xs text-[var(--text-secondary)]" role="status">
            Weather grid unavailable (the free weather service limits requests per minute). Routes are still valid.
            <button type="button" className="link-button" onClick={onRetryHeatmap}>
              Retry
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

function Legend({ layer }: { layer: HeatLayer }) {
  if (layer === "risk") {
    return (
      <ul className="legend" aria-label="Risk levels">
        {LEVELS.map((l) => (
          <li key={l.key}>
            <span className="swatch" style={{ background: l.color }} />
            {l.label}
          </li>
        ))}
      </ul>
    );
  }
  const bands = VARIABLE_BANDS[layer];
  return (
    <ul className="legend" aria-label={`${layer} in ${bands.unit}`}>
      {bands.labels.map((label, i) => (
        <li key={label}>
          <span className="swatch" style={{ background: BAND_COLORS[i] }} />
          {label}
        </li>
      ))}
      <li className="text-[var(--text-muted)]">{bands.unit}</li>
    </ul>
  );
}
