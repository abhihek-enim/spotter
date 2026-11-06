import { useEffect, useId, useRef, useState } from "react";
import { api, type Place } from "../api";

interface Props {
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
  placeholder?: string;
}

/** Text box with place suggestions from /api/geocode (debounced, keyboard friendly). */
export function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const id = useId();
  const [text, setText] = useState(value?.label ?? "");
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const skipNextSearch = useRef(false);
  const lastEmitted = useRef<Place | null>(value);

  function emit(place: Place | null) {
    lastEmitted.current = place;
    onChange(place);
  }

  // Show the label when the parent sets a place itself (the example trip, or Swap).
  useEffect(() => {
    if (value === lastEmitted.current) return; // our own change: leave the text alone
    lastEmitted.current = value;
    skipNextSearch.current = true;
    setText(value?.label ?? "");
    setOpen(false);
  }, [value]);

  useEffect(() => {
    if (skipNextSearch.current) {
      skipNextSearch.current = false;
      return;
    }
    const query = text.trim();
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .geocode(query, controller.signal)
        .then((places) => {
          setResults(places);
          setActive(0);
          setOpen(true);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Search failed");
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [text]);

  function choose(place: Place) {
    emit(place);
    skipNextSearch.current = true;
    setText(place.label);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const listId = `${id}-list`;
  return (
    <div className="relative">
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <input
        id={id}
        className="field"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && results[active] ? `${listId}-${active}` : undefined}
        autoComplete="off"
        placeholder={placeholder}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (value) emit(null); // typing again clears the chosen place
        }}
        onKeyDown={onKeyDown}
        onFocus={() => results.length > 0 && !value && setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
      />
      {error && <p className="mt-1 text-xs text-[var(--critical-text)]">{error}</p>}
      {open && results.length > 0 && (
        <ul id={listId} role="listbox" className="suggestions">
          {results.map((place, i) => (
            <li
              key={`${place.label}-${place.lat}-${place.lon}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "suggestion active" : "suggestion"}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(place);
              }}
              onMouseEnter={() => setActive(i)}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
      {open && results.length === 0 && text.trim().length >= 2 && (
        <ul id={listId} role="listbox" className="suggestions">
          <li className="suggestion text-[var(--text-muted)]">No matching places in the US or Canada</li>
        </ul>
      )}
    </div>
  );
}
