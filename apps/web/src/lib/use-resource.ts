"use client";

// Loads data from the API in a Client Component and keeps it fresh.
//
// Cross-client sync (buildguide.md "Notes on cross-client sync", CLAUDE.md
// §8): there is no live push in v1. Instead, screens re-fetch when the tab
// regains focus or becomes visible again, so a bill edited on another
// device is current as soon as you come back to it. `pollMs` adds a timer
// on top (used only while a receipt is being processed).

import { useCallback, useEffect, useRef, useState } from "react";

import { errorMessage } from "./api";

export interface Resource<T> {
  data: T | undefined;
  error: string | null;
  /** True until the first response for the current inputs arrives. */
  loading: boolean;
  /** Re-fetch now. Resolves when done; never throws. */
  reload: () => Promise<void>;
  /** Replace the data locally (e.g. with a mutation's response). */
  setData: (value: T) => void;
}

interface State<T> {
  /** Which inputs this data/error belongs to. */
  key: string | null;
  data: T | undefined;
  error: string | null;
}

export function useResource<T>(
  load: () => Promise<T>,
  deps: unknown[],
  options: { pollMs?: number; refetchOnFocus?: boolean } = {},
): Resource<T> {
  const { pollMs, refetchOnFocus = true } = options;
  const depsKey = JSON.stringify(deps);
  const [state, setState] = useState<State<T>>({ key: null, data: undefined, error: null });

  // Latest loader and inputs, for callbacks that outlive a render.
  const loadRef = useRef(load);
  const keyRef = useRef(depsKey);
  const requestId = useRef(0);
  useEffect(() => {
    loadRef.current = load;
    keyRef.current = depsKey;
  });

  const reload = useCallback(async () => {
    const id = ++requestId.current;
    const key = keyRef.current;
    try {
      const data = await loadRef.current();
      if (id === requestId.current) setState({ key, data, error: null });
    } catch (e) {
      if (id === requestId.current) {
        // Keep showing the last good data on a failed background refresh.
        setState((prev) => ({
          key,
          data: prev.key === key ? prev.data : undefined,
          error: errorMessage(e),
        }));
      }
    }
  }, []);

  useEffect(() => {
    keyRef.current = depsKey;
    void reload();
  }, [depsKey, reload]);

  useEffect(() => {
    if (!refetchOnFocus) return;
    const onVisible = () => {
      if (document.visibilityState === "visible") void reload();
    };
    window.addEventListener("focus", onVisible);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", onVisible);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refetchOnFocus, reload]);

  useEffect(() => {
    if (!pollMs) return;
    const timer = window.setInterval(() => void reload(), pollMs);
    return () => window.clearInterval(timer);
  }, [pollMs, reload]);

  const setData = useCallback((value: T) => {
    setState((prev) => ({ ...prev, data: value, error: null }));
  }, []);

  const current = state.key === depsKey;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : null,
    loading: !current,
    reload,
    setData,
  };
}
