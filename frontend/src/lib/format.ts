// Times are shown in the viewer's own time zone, with the zone named.

const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

export const zoneName = () =>
  new Intl.DateTimeFormat(undefined, { timeZoneName: "short" }).formatToParts(new Date()).find((p) => p.type === "timeZoneName")
    ?.value ?? timeZone;

export function formatClock(iso: string | Date): string {
  return new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h > 0 ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}

export const formatMiles = (miles: number) => `${miles.toLocaleString(undefined, { maximumFractionDigits: 1 })} mi`;

/** Value for an <input type="datetime-local">: local time, minutes precision. */
export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Now, rounded up to the next quarter hour. */
export function nextQuarterHour(now = new Date()): Date {
  const d = new Date(now);
  d.setSeconds(0, 0);
  d.setMinutes(Math.ceil((d.getMinutes() + 1) / 15) * 15);
  return d;
}

export function slotWindow(slot0Start: string, hour: number): { start: Date; end: Date } {
  const start = new Date(new Date(slot0Start).getTime() + hour * 3_600_000);
  return { start, end: new Date(start.getTime() + 3_600_000) };
}
