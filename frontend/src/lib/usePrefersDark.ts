import { useEffect, useState } from "react";

const query = "(prefers-color-scheme: dark)";

/** True while the viewer's system is in dark mode (updates live). */
export function usePrefersDark(): boolean {
  const [dark, setDark] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setDark(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return dark;
}
