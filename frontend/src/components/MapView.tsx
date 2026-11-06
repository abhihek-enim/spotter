import type { FeatureCollection, LineString, Point } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState } from "react";
import Map, {
  Layer,
  Marker,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from "react-map-gl/maplibre";
import type { Checkpoint, Heatmap, Level, TripResult } from "../api";
import { formatClock } from "../lib/format";
import { heatmapGeoJSON, heatmapPaint, type HeatLayer } from "../lib/heatmap";
import { levelColor, levelColorExpression, levelLabel } from "../lib/risk";
import { boundsOf, midpoint, positionAt } from "../lib/route";
import { usePrefersDark } from "../lib/usePrefersDark";

const STYLES = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};
const INITIAL_VIEW = { longitude: -96, latitude: 38.5, zoom: 3.6 };

export interface Focus {
  routeId: string;
  index: number;
  nonce: number; // changes on every request, so the same checkpoint can be focused twice
}

interface Props {
  result: TripResult | null;
  heatmap: Heatmap | null; // arrives a moment after the routes
  selectedId: string | null;
  onSelect: (id: string) => void;
  hour: number;
  heatLayer: HeatLayer;
  focus: Focus | null;
}

export function MapView({ result, heatmap, selectedId, onSelect, hour, heatLayer, focus }: Props) {
  const mapRef = useRef<MapRef>(null);
  const dark = usePrefersDark();
  const [labelLayerId, setLabelLayerId] = useState<string | undefined>();
  const [popup, setPopup] = useState<{ routeId: string; index: number } | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; cell: number } | null>(null);
  const [cursor, setCursor] = useState("");

  // Data for the map, built once per trip. Moving the slider changes paint only.
  const heat = useMemo(() => (heatmap ? heatmapGeoJSON(heatmap) : null), [heatmap]);
  const routeLines = useMemo<FeatureCollection<LineString>>(
    () => ({
      type: "FeatureCollection",
      features: (result?.routes ?? []).map((r) => ({
        type: "Feature",
        properties: { id: r.id },
        geometry: { type: "LineString", coordinates: r.line },
      })),
    }),
    [result],
  );
  const routeLabels = useMemo<FeatureCollection<Point>>(
    () => ({
      type: "FeatureCollection",
      features: (result?.routes ?? []).map((r) => ({
        type: "Feature",
        properties: { id: r.id },
        geometry: { type: "Point", coordinates: midpoint(r) },
      })),
    }),
    [result],
  );
  const checkpoints = useMemo<FeatureCollection<Point>>(
    () => ({
      type: "FeatureCollection",
      features: (result?.routes ?? []).flatMap((r) =>
        r.checkpoints.map((c, index) => ({
          type: "Feature" as const,
          properties: { route: r.id, index, level: c.risk.level, slot: c.slot },
          geometry: { type: "Point" as const, coordinates: [c.lon, c.lat] },
        })),
      ),
    }),
    [result],
  );
  const selected = result?.routes.find((r) => r.id === selectedId) ?? null;
  const riskLines = useMemo<FeatureCollection<LineString>>(
    () => ({
      type: "FeatureCollection",
      features: (selected?.risk_segments ?? []).map((s) => ({
        type: "Feature",
        properties: { level: s.level },
        geometry: { type: "LineString", coordinates: s.coordinates },
      })),
    }),
    [selected],
  );
  const heatPaint = useMemo(() => heatmapPaint(heatLayer, hour), [heatLayer, hour]);
  const truck = selected ? positionAt(selected, hour * 3600) : null;

  // Fit the map to the routes whenever a new trip arrives.
  useEffect(() => {
    if (!result || !mapRef.current) return;
    setPopup(null);
    mapRef.current.fitBounds(boundsOf(result.routes), { padding: { top: 60, bottom: 170, left: 50, right: 50 }, duration: 900 });
  }, [result]);

  // Fly to a checkpoint picked in the table.
  useEffect(() => {
    if (!focus || !result || !mapRef.current) return;
    const c = result.routes.find((r) => r.id === focus.routeId)?.checkpoints[focus.index];
    if (!c) return;
    mapRef.current.flyTo({ center: [c.lon, c.lat], zoom: Math.max(mapRef.current.getZoom(), 8), duration: 700 });
    setPopup({ routeId: focus.routeId, index: focus.index });
  }, [focus, result]);

  function onClick(e: MapLayerMouseEvent) {
    const feature = e.features?.[0];
    if (!feature) return setPopup(null);
    const props = feature.properties as Record<string, unknown>;
    if (feature.layer.id === "checkpoints") {
      onSelect(String(props.route));
      setPopup({ routeId: String(props.route), index: Number(props.index) });
    } else if (feature.layer.id === "route-hit" || feature.layer.id === "route-labels") {
      onSelect(String(props.id));
    }
  }

  function onMouseMove(e: MapLayerMouseEvent) {
    const feature = e.features?.[0];
    const clickable = feature && feature.layer.id !== "heat-fill";
    setCursor(clickable ? "pointer" : "");
    if (feature?.layer.id === "heat-fill") {
      setHover({ x: e.point.x, y: e.point.y, cell: Number((feature.properties as { i: number }).i) });
    } else {
      setHover(null);
    }
  }

  const popupCheckpoint: Checkpoint | undefined = popup
    ? result?.routes.find((r) => r.id === popup.routeId)?.checkpoints[popup.index]
    : undefined;
  const sel = selectedId ?? "";

  return (
    <div className="relative h-full w-full">
      <Map
        ref={mapRef}
        initialViewState={INITIAL_VIEW}
        mapStyle={dark ? STYLES.dark : STYLES.light}
        interactiveLayerIds={["checkpoints", "route-hit", "route-labels", "heat-fill"]}
        onClick={onClick}
        onMouseMove={onMouseMove}
        onMouseLeave={() => setHover(null)}
        cursor={cursor}
        onLoad={(e) => setLabelLayerId(e.target.getStyle().layers.find((l) => l.type === "symbol")?.id)}
        onStyleData={(e) => {
          const map = e.target;
          if (map.isStyleLoaded()) setLabelLayerId(map.getStyle().layers.find((l) => l.type === "symbol")?.id);
        }}
        attributionControl={{ compact: true, customAttribution: "Weather: Open-Meteo.com" }}
      >
        <NavigationControl position="top-right" showCompass={false} />

        {heat && (
          <Source id="heat" type="geojson" data={heat}>
            {/* Under the basemap's labels so city names stay readable. */}
            <Layer id="heat-fill" type="fill" beforeId={labelLayerId} paint={heatPaint as never} />
          </Source>
        )}

        <Source id="routes" type="geojson" data={routeLines}>
          <Layer
            id="route-casing"
            type="line"
            layout={{ "line-cap": "round", "line-join": "round" }}
            paint={{ "line-color": dark ? "#0c0c0c" : "#ffffff", "line-width": 8 }}
          />
          <Layer
            id="route-other"
            type="line"
            filter={["!=", ["get", "id"], sel]}
            layout={{ "line-cap": "round", "line-join": "round" }}
            paint={{ "line-color": dark ? "#9a9890" : "#77756f", "line-width": 4.5 }}
          />
          <Layer id="route-hit" type="line" filter={["!=", ["get", "id"], sel]} paint={{ "line-width": 16, "line-opacity": 0 }} />
        </Source>

        <Source id="risk" type="geojson" data={riskLines}>
          <Layer
            id="risk-casing"
            type="line"
            layout={{ "line-cap": "round", "line-join": "round" }}
            paint={{ "line-color": dark ? "#f0efec" : "#1b1b1b", "line-width": 9, "line-opacity": 0.75 }}
          />
          <Layer
            id="risk-line"
            type="line"
            layout={{ "line-cap": "round", "line-join": "round" }}
            paint={{ "line-color": levelColorExpression("level") as never, "line-width": 6 }}
          />
        </Source>

        <Source id="checkpoints" type="geojson" data={checkpoints}>
          <Layer
            id="checkpoints"
            type="circle"
            paint={{
              "circle-color": levelColorExpression("level") as never,
              // Bigger on the selected route, biggest where the truck is during the slider's hour.
              "circle-radius": [
                "case",
                ["all", ["==", ["get", "route"], sel], ["==", ["get", "slot"], hour]], 8.5,
                ["==", ["get", "route"], sel], 5.5,
                3.5,
              ] as never,
              "circle-stroke-color": dark ? "#f0efec" : "#1b1b1b",
              "circle-stroke-width": ["case", ["==", ["get", "route"], sel], 1.5, 0.75] as never,
              "circle-opacity": ["case", ["==", ["get", "route"], sel], 1, 0.6] as never,
              "circle-stroke-opacity": ["case", ["==", ["get", "route"], sel], 1, 0.6] as never,
            }}
          />
        </Source>

        <Source id="route-labels" type="geojson" data={routeLabels}>
          <Layer
            id="route-labels"
            type="symbol"
            layout={{
              "text-field": ["get", "id"],
              "text-font": ["Noto Sans Bold"],
              "text-size": 15,
              "text-allow-overlap": true,
            }}
            paint={{
              "text-color": dark ? "#f0efec" : "#0b0b0b",
              "text-halo-color": dark ? "#0c0c0c" : "#ffffff",
              "text-halo-width": 3,
            }}
          />
        </Source>

        {result && (
          <>
            <Marker longitude={result.trip.origin.lon} latitude={result.trip.origin.lat} anchor="bottom">
              <span className="pin" title={result.trip.origin.label}>
                Start
              </span>
            </Marker>
            <Marker longitude={result.trip.destination.lon} latitude={result.trip.destination.lat} anchor="bottom">
              <span className="pin" title={result.trip.destination.label}>
                End
              </span>
            </Marker>
          </>
        )}

        {truck && selected && (
          <Marker longitude={truck.at[0]} latitude={truck.at[1]} anchor="center">
            <span className="truck" title={truck.arrived ? "Arrived" : `Route ${selected.id}, +${hour} h`} aria-label="Truck position">
              🚚
            </span>
          </Marker>
        )}

        {popup && popupCheckpoint && (
          <Popup
            longitude={popupCheckpoint.lon}
            latitude={popupCheckpoint.lat}
            anchor="bottom"
            offset={12}
            onClose={() => setPopup(null)}
            closeOnClick={false}
            maxWidth="280px"
          >
            <CheckpointDetails routeId={popup.routeId} checkpoint={popupCheckpoint} />
          </Popup>
        )}
      </Map>

      {hover && heatmap && <CellTooltip heatmap={heatmap} cell={hover.cell} hour={hour} x={hover.x} y={hover.y} />}
    </div>
  );
}

function RiskBadge({ level }: { level: Level }) {
  return (
    <span className="inline-flex items-center gap-1 font-semibold">
      <span className="swatch" style={{ background: levelColor(level) }} />
      {levelLabel(level)}
    </span>
  );
}

function CheckpointDetails({ routeId, checkpoint: c }: { routeId: string; checkpoint: Checkpoint }) {
  return (
    <div className="space-y-1 text-[13px] leading-snug text-[#0b0b0b]">
      <p className="font-semibold">
        Route {routeId} · mile {c.mile}
      </p>
      <p>
        ETA <strong>{formatClock(c.eta)}</strong> <span className="text-[#52514e]">(forecast hour +{c.slot})</span>
      </p>
      <table className="w-full text-[12px]">
        <tbody>
          <tr>
            <td>Wind</td>
            <td>
              {Math.round(c.weather.wind_mph)} mph <span className="text-[#52514e]">(gusts {Math.round(c.weather.gust_mph)})</span>
            </td>
            <td>
              <RiskBadge level={c.risk.wind} />
            </td>
          </tr>
          <tr>
            <td>Rain</td>
            <td>{c.weather.rain_in_hr.toFixed(2)} in/hr</td>
            <td>
              <RiskBadge level={c.risk.rain} />
            </td>
          </tr>
          <tr>
            <td>Snow</td>
            <td>{c.weather.snow_in_hr.toFixed(1)} in/hr</td>
            <td>
              <RiskBadge level={c.risk.snow} />
            </td>
          </tr>
        </tbody>
      </table>
      <p className="border-t border-[#e1e0d9] pt-1">
        Risk <RiskBadge level={c.risk.level} />: {c.risk.reason}
      </p>
      <p className="text-[11px] text-[#52514e]">Stands for {c.covers_mi} mi of road (nearest checkpoint).</p>
    </div>
  );
}

function CellTooltip({ heatmap: h, cell, hour, x, y }: { heatmap: Heatmap; cell: number; hour: number; x: number; y: number }) {
  return (
    <div className="cell-tooltip" style={{ left: x + 14, top: y + 14 }} role="status">
      <RiskBadge level={h.risk[cell][hour]} />
      <div>
        Wind {Math.round(h.wind[cell][hour])} mph · Rain {h.rain[cell][hour].toFixed(2)} in/hr · Snow{" "}
        {h.snow[cell][hour].toFixed(1)} in/hr
      </div>
    </div>
  );
}
