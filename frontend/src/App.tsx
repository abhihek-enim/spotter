import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type Health, type Heatmap, type TripInput, type TripResult } from "./api";
import { CheckpointTable } from "./components/CheckpointTable";
import { MapView, type Focus } from "./components/MapView";
import { RouteCards } from "./components/RouteCards";
import { TimeControls } from "./components/TimeControls";
import { TripForm } from "./components/TripForm";
import type { HeatLayer } from "./lib/heatmap";

type ServerState = { kind: "connecting" } | { kind: "waking" } | { kind: "ready"; health: Health } | { kind: "down" };

export default function App() {
  const [server, setServer] = useState<ServerState>({ kind: "connecting" });
  const [result, setResult] = useState<TripResult | null>(null);
  const [heatmap, setHeatmap] = useState<Heatmap | "loading" | "failed" | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hour, setHour] = useState(0);
  const [heatLayer, setHeatLayer] = useState<HeatLayer>("risk");
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<Focus | null>(null);
  const inFlight = useRef<AbortController | null>(null);
  const lastInput = useRef<TripInput | null>(null);

  // The 0-48 h corridor grid: one request per trip, after which the slider is local.
  const loadHeatmap = useCallback((input: TripInput, signal: AbortSignal) => {
    setHeatmap("loading");
    api
      .heatmap(input, signal)
      .then(setHeatmap)
      .catch(() => {
        if (!signal.aborted) setHeatmap("failed");
      });
  }, []);

  // Ping the API on load. On free hosting this also wakes a sleeping server early.
  useEffect(() => {
    const slow = window.setTimeout(() => setServer((s) => (s.kind === "connecting" ? { kind: "waking" } : s)), 2500);
    api
      .health()
      .then((health) => setServer({ kind: "ready", health }))
      .catch(() => setServer({ kind: "down" }))
      .finally(() => window.clearTimeout(slow));
    return () => window.clearTimeout(slow);
  }, []);

  const plan = useCallback(async (input: TripInput) => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    lastInput.current = input;
    setBusy(true);
    setError(null);
    setPlaying(false);
    setHeatmap(null);
    try {
      const trip = await api.planTrip(input, controller.signal);
      setResult(trip);
      setSelectedId(trip.recommendation.route_id);
      setHour(0);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      return;
    } finally {
      if (inFlight.current === controller) setBusy(false);
    }
    loadHeatmap(input, controller.signal); // routes are on screen; the grid follows
  }, [loadHeatmap]);

  const retryHeatmap = useCallback(() => {
    if (lastInput.current && inFlight.current) loadHeatmap(lastInput.current, inFlight.current.signal);
  }, [loadHeatmap]);

  const onHour = useCallback((h: number) => setHour(h), []);
  const onFocusCheckpoint = useCallback(
    (index: number) => setFocus({ routeId: selectedId ?? "", index, nonce: Date.now() }),
    [selectedId],
  );
  const selected = result?.routes.find((r) => r.id === selectedId) ?? null;

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="mb-4">
          <h1 className="text-xl font-semibold tracking-tight">Weather-Aware Truck Routing</h1>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">
            Three routes, weather at every checkpoint when the truck gets there, and the safest pick.
          </p>
          <ServerStatus state={server} />
        </header>

        <TripForm busy={busy} onSubmit={plan} />

        {error && (
          <div role="alert" className="callout callout-danger mt-4 text-sm">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-5 space-y-3">
            {result.notes.length > 0 && (
              <ul className="space-y-1 text-xs text-[var(--text-secondary)]">
                {result.notes.map((n) => (
                  <li key={n}>ℹ {n}</li>
                ))}
              </ul>
            )}
            <RouteCards result={result} selectedId={selectedId ?? ""} onSelect={setSelectedId} />
            {selected && (
              <CheckpointTable route={selected} onFocus={onFocusCheckpoint} />
            )}
          </div>
        )}

        <footer className="mt-6 text-[11px] leading-relaxed text-[var(--text-muted)]">
          Weather: Open-Meteo forecast (wind, rain + showers, snowfall). Map © OpenFreeMap, OpenMapTiles, OpenStreetMap
          contributors. Risk uses sustained wind; gusts are shown for reference.
        </footer>
      </aside>

      <main className="map-area" aria-label="Map">
        <MapView
          result={result}
          heatmap={typeof heatmap === "object" ? heatmap : null}
          selectedId={selectedId}
          onSelect={setSelectedId}
          hour={hour}
          heatLayer={heatLayer}
          focus={focus}
        />
        {result && selectedId && (
          <TimeControls
            result={result}
            heatmapState={heatmap === null || typeof heatmap === "object" ? "ready" : heatmap}
            onRetryHeatmap={retryHeatmap}
            selectedId={selectedId}
            hour={hour}
            onHour={onHour}
            layer={heatLayer}
            onLayer={setHeatLayer}
            playing={playing}
            onPlaying={setPlaying}
          />
        )}
        {!result && !busy && (
          <div className="map-hint">Choose an origin and destination to compare routes. The map shows weather risk along each one.</div>
        )}
        {busy && <BusyHint />}
      </main>
    </div>
  );
}

/** Loading note. After 10 s it says plainly that long truck routes can take up to a minute. */
function BusyHint() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), 10_000);
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <div className="map-hint" role="status">
      Finding truck routes, then reading the forecast at each checkpoint's arrival time…
      {slow && (
        <p className="mt-1 text-xs text-[var(--text-secondary)]">
          Long trips can take up to a minute the first time while the routing and weather services answer. Repeat
          trips are much faster.
        </p>
      )}
    </div>
  );
}

function ServerStatus({ state }: { state: ServerState }) {
  const text =
    state.kind === "connecting"
      ? "Connecting to the server…"
      : state.kind === "waking"
        ? "Waking up the server (free hosting sleeps when idle; this can take up to a minute)…"
        : state.kind === "down"
          ? "The server is not answering. Try reloading the page."
          : `Ready · routing by ${state.health.routing}`;
  const dot = state.kind === "ready" ? "var(--good)" : state.kind === "down" ? "var(--critical-text)" : "var(--text-muted)";
  return (
    <p className="mt-2 flex items-center gap-1.5 text-xs text-[var(--text-secondary)]" role="status">
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} />
      {text}
    </p>
  );
}
