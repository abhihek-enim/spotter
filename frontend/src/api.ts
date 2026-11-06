// Types for the Django API (backend/trips/service.py builds these shapes) and the fetch helpers.

export type Level = 0 | 1 | 2 | 3 | 4;
export type LngLat = [number, number];

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface Checkpoint {
  mile: number;
  lat: number;
  lon: number;
  eta: string; // ISO UTC
  slot: number; // forecast hour index, 0 = hour of departure
  covers_mi: number;
  weather: { wind_mph: number; gust_mph: number; rain_in_hr: number; snow_in_hr: number };
  risk: { level: Level; wind: Level; rain: Level; snow: Level; load_rule: boolean; reason: string };
}

export interface Route {
  id: string;
  label: string;
  distance_mi: number;
  duration_s: number;
  arrival: string;
  line: LngLat[];
  line_times_s: number[];
  risk_segments: { level: Level; coordinates: LngLat[] }[];
  summary: {
    miles_by_level: { low: number; moderate: number; high: number; severe: number; no_travel: number };
    average_risk: number;
    worst: Level;
  };
  checkpoints: Checkpoint[];
  rank: number;
  recommended: boolean;
}

export interface Heatmap {
  step_deg: number;
  slot0_start: string; // slot k covers [slot0_start + k h, + 1 h)
  slots: number;
  cells: LngLat[];
  risk: Level[][];
  wind: number[][];
  rain: number[][];
  snow: number[][];
}

export interface TripResult {
  trip: { origin: Place; destination: Place; departure: string; load_lb: number; spacing_mi: number };
  provider: { name: string; truck_routing: boolean };
  routes: Route[];
  recommendation: { route_id: string; ranking: string[]; reason: string; all_routes_have_no_travel: boolean };
  notes: string[];
}

export interface TripInput {
  origin: Place;
  destination: Place;
  departure: string; // ISO with time zone
  load_lb: number;
  spacing_mi: 10 | 25 | 50;
}

export interface Health {
  ok: boolean;
  routing: string;
  truck_routing: boolean;
}

export class ApiError extends Error {}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(errorText(body) ?? `Request failed (HTTP ${response.status}).`);
  }
  return body as T;
}

/** DRF errors come as {"detail": "..."} or {"field": ["message"]}. */
function errorText(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const entries = Object.entries(body as Record<string, unknown>);
  const parts = entries.map(([field, value]) => {
    const message = Array.isArray(value) ? value.join(" ") : typeof value === "object" ? errorText(value) : String(value);
    return field === "detail" || field === "non_field_errors" ? message : `${field.replace("_", " ")}: ${message}`;
  });
  return parts.join(" ") || null;
}

export const api = {
  health: () => request<Health>("/api/health"),
  geocode: (q: string, signal?: AbortSignal) =>
    request<{ results: Place[] }>(`/api/geocode?q=${encodeURIComponent(q)}`, { signal }).then((r) => r.results),
  planTrip: (input: TripInput, signal?: AbortSignal) => post<TripResult>("/api/trips", input, signal),
  // Same input; call after planTrip so the server reuses the routes it just cached.
  heatmap: (input: TripInput, signal?: AbortSignal) => post<Heatmap>("/api/trips/heatmap", input, signal),
};

function post<T>(url: string, body: unknown, signal?: AbortSignal) {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}
