import { memo } from "react";
import type { Route, TripResult } from "../api";
import { formatClock, formatDuration, formatMiles } from "../lib/format";
import { LEVELS, levelLabel } from "../lib/risk";

interface Props {
  result: TripResult;
  selectedId: string;
  onSelect: (id: string) => void;
}

// memo: the slider re-renders the page every hour step; these cards do not depend on the hour.
export const RouteCards = memo(function RouteCards({ result, selectedId, onSelect }: Props) {
  const ordered = [...result.routes].sort((a, b) => a.rank - b.rank);
  const rec = result.recommendation;
  return (
    <section aria-label="Route options" className="space-y-3">
      <div className={rec.all_routes_have_no_travel ? "callout callout-danger" : "callout callout-good"}>
        <p className="font-semibold">
          {rec.all_routes_have_no_travel ? "⚠ No safe route at this departure time" : `✓ Recommended: Route ${rec.route_id}`}
        </p>
        <p className="text-sm">{rec.all_routes_have_no_travel ? `Least bad: Route ${rec.route_id}. ${rec.reason}` : rec.reason}</p>
      </div>
      {ordered.map((route) => (
        <RouteCard key={route.id} route={route} selected={route.id === selectedId} onSelect={() => onSelect(route.id)} />
      ))}
    </section>
  );
});

function RouteCard({ route, selected, onSelect }: { route: Route; selected: boolean; onSelect: () => void }) {
  const miles = route.summary.miles_by_level;
  const total = route.distance_mi || 1;
  return (
    <button type="button" onClick={onSelect} aria-pressed={selected} className={selected ? "route-card selected" : "route-card"}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-base font-semibold">
          Route {route.id}
          {route.label && <span className="ml-1 font-normal text-[var(--text-secondary)]">via {route.label}</span>}
        </span>
        <span className="text-xs text-[var(--text-muted)]">#{route.rank}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 text-sm text-[var(--text-secondary)]">
        <span>{formatDuration(route.duration_s)}</span>
        <span>{formatMiles(route.distance_mi)}</span>
        <span>arrives {formatClock(route.arrival)}</span>
      </div>

      {/* Miles at each risk level, as one stacked bar with a 2px gap between parts. */}
      <div className="risk-bar mt-2" aria-hidden="true">
        {LEVELS.map((l) =>
          miles[l.key] > 0 ? <span key={l.key} style={{ flexGrow: miles[l.key] / total, background: l.color }} /> : null,
        )}
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
        {LEVELS.filter((l) => miles[l.key] > 0).map((l) => (
          <li key={l.key} className="flex items-center gap-1">
            <span className="swatch" style={{ background: l.color }} />
            {l.label} {formatMiles(miles[l.key])}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        Average risk {route.summary.average_risk.toFixed(2)} of 4 · worst {levelLabel(route.summary.worst)}
      </p>
    </button>
  );
}
