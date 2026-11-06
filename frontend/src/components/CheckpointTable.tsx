import { memo } from "react";
import type { Route } from "../api";
import { formatClock } from "../lib/format";
import { levelColor, levelLabel } from "../lib/risk";

interface Props {
  route: Route;
  onFocus: (index: number) => void;
}

/** Every checkpoint of the selected route as a table: the text view of what the map shows. */
export const CheckpointTable = memo(function CheckpointTable({ route, onFocus }: Props) {
  return (
    <details className="table-wrap">
      <summary className="cursor-pointer text-sm font-semibold">
        Route {route.id} checkpoints ({route.checkpoints.length})
      </summary>
      <div className="mt-2 max-h-80 overflow-auto">
        <table className="w-full text-xs tabular-nums">
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Wind (gust)</th>
              <th>Rain</th>
              <th>Snow</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((c, i) => (
              <tr key={c.mile} onClick={() => onFocus(i)} className="cursor-pointer" title={c.risk.reason}>
                <td>{c.mile}</td>
                <td>{formatClock(c.eta)}</td>
                <td>
                  {Math.round(c.weather.wind_mph)} ({Math.round(c.weather.gust_mph)})
                </td>
                <td>{c.weather.rain_in_hr.toFixed(2)}</td>
                <td>{c.weather.snow_in_hr.toFixed(1)}</td>
                <td>
                  <span className="inline-flex items-center gap-1">
                    <span className="swatch" style={{ background: levelColor(c.risk.level) }} />
                    {levelLabel(c.risk.level)}
                    {c.risk.load_rule && " ⚖"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
          Wind in mph, rain and snow in inches per hour. ⚖ = raised by the load rule.
        </p>
      </div>
    </details>
  );
});
