import { memo, useState } from "react";
import type { Place, TripInput } from "../api";
import { nextQuarterHour, toLocalInputValue, zoneName } from "../lib/format";
import { PlaceInput } from "./PlaceInput";

const EXAMPLE = {
  origin: { label: "Dallas, Texas, US", lat: 32.78306, lon: -96.80667 },
  destination: { label: "Chicago, Illinois, US", lat: 41.85003, lon: -87.65005 },
};

interface Props {
  busy: boolean;
  onSubmit: (input: TripInput) => void;
}

export const TripForm = memo(function TripForm({ busy, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [departure, setDeparture] = useState(() => toLocalInputValue(nextQuarterHour()));
  const [load, setLoad] = useState("35000");
  const [spacing, setSpacing] = useState<10 | 25 | 50>(25);
  const [problem, setProblem] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const loadLb = Number(load);
    if (!origin || !destination) return setProblem("Pick the origin and destination from the suggestions.");
    if (!departure) return setProblem("Enter a departure date and time.");
    if (!Number.isFinite(loadLb) || loadLb < 0 || loadLb > 80_000) return setProblem("Load weight must be 0–80,000 lb.");
    setProblem(null);
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(), // datetime-local is read as the viewer's local time
      load_lb: Math.round(loadLb),
      spacing_mi: spacing,
    });
  }

  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <PlaceInput label="Origin" value={origin} onChange={setOrigin} placeholder="City, e.g. Dallas" />
      <div className="flex justify-end -my-1">
        <button
          type="button"
          className="link-button"
          onClick={() => {
            setOrigin(destination);
            setDestination(origin);
          }}
        >
          ⇅ Swap
        </button>
      </div>
      <PlaceInput label="Destination" value={destination} onChange={setDestination} placeholder="City, e.g. Chicago" />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="departure" className="field-label">
            Departure <span className="font-normal text-[var(--text-muted)]">({zoneName()})</span>
          </label>
          <input
            id="departure"
            type="datetime-local"
            className="field"
            value={departure}
            onChange={(e) => setDeparture(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="load" className="field-label">
            Load weight (lb)
          </label>
          <input
            id="load"
            type="number"
            inputMode="numeric"
            min={0}
            max={80000}
            step={500}
            className="field"
            value={load}
            onChange={(e) => setLoad(e.target.value)}
          />
        </div>
      </div>

      <fieldset>
        <legend className="field-label">Weather checkpoint every</legend>
        <div className="segmented" role="radiogroup">
          {([10, 25, 50] as const).map((miles) => (
            <label key={miles} className={spacing === miles ? "segment selected" : "segment"}>
              <input
                type="radio"
                name="spacing"
                value={miles}
                checked={spacing === miles}
                onChange={() => setSpacing(miles)}
                className="sr-only"
              />
              {miles} mi
            </label>
          ))}
        </div>
      </fieldset>

      {problem && (
        <p role="alert" className="text-sm text-[var(--critical-text)]">
          {problem}
        </p>
      )}

      <div className="flex items-center gap-3">
        <button type="submit" className="primary-button" disabled={busy}>
          {busy ? "Checking routes and weather…" : "Compare routes"}
        </button>
        <button
          type="button"
          className="link-button"
          onClick={() => {
            setOrigin(EXAMPLE.origin);
            setDestination(EXAMPLE.destination);
          }}
        >
          Try Dallas → Chicago
        </button>
      </div>
    </form>
  );
});
