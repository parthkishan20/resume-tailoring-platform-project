"use client";

import * as React from "react";

/**
 * Layout preferences that survive a reload: the nav collapse state, the
 * inspector width, the editor/preview split ratio (DESIGN-SYSTEM.md 2.4, which
 * specifies the inspector as "resizable 320-560, persisted").
 *
 * Every read and write is wrapped: `localStorage` throws outright in a private
 * window and in an iframe with site data blocked, and a layout preference is
 * never worth taking the app down for. A failed read means "no preference",
 * which is exactly the initial value.
 */
const PREFIX = "resumetailor.layout.";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(PREFIX + key, value);
  } catch {
    // A preference that cannot be stored is not an error worth surfacing.
  }
}

/**
 * State backed by `localStorage`, hydration-safe.
 *
 * The first render always returns `initial`, on the server and on the client
 * alike, and the stored value is adopted in an effect. Reading storage during
 * render would produce markup the server cannot have produced, which React
 * reports as a hydration mismatch and then discards.
 */
export function usePersistedState<T>(
  key: string,
  initial: T,
  parse: (raw: string) => T | null,
  serialize: (value: T) => string,
): [T, (next: T) => void] {
  const [value, setValue] = React.useState<T>(initial);

  React.useEffect(() => {
    const raw = read(key);
    if (raw === null) return;
    const parsed = parse(raw);
    if (parsed !== null) setValue(parsed);
    // `parse` and `serialize` are inline literals at every call site; running
    // this once per key is the intent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = React.useCallback(
    (next: T) => {
      setValue(next);
      write(key, serialize(next));
    },
    // Same reasoning as above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );

  return [value, set];
}

export function usePersistedNumber(
  key: string,
  initial: number,
  min: number,
  max: number,
): [number, (next: number) => void] {
  return usePersistedState<number>(
    key,
    initial,
    (raw) => {
      const parsed = Number.parseFloat(raw);
      return Number.isFinite(parsed) ? Math.min(Math.max(parsed, min), max) : null;
    },
    (value) => String(value),
  );
}

export function usePersistedBoolean(
  key: string,
  initial: boolean,
): [boolean, (next: boolean) => void] {
  return usePersistedState<boolean>(
    key,
    initial,
    (raw) => (raw === "true" ? true : raw === "false" ? false : null),
    (value) => String(value),
  );
}
