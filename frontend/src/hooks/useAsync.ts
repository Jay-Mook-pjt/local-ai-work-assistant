"use client";

import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";

interface AsyncState<T> {
  data: T | undefined;
  error: Error | null;
  loading: boolean;
  reload: () => void;
  setData: (v: T) => void;
}

/**
 * Runs an async loader on mount / when deps change.
 * `pollMs` re-runs it on an interval while `shouldPoll(data)` is true.
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: DependencyList,
  opts: { pollMs?: number; shouldPoll?: (data: T | undefined) => boolean } = {},
): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  const optsRef = useRef(opts);
  useEffect(() => {
    loaderRef.current = loader;
    optsRef.current = opts;
  });

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const run = () =>
      loaderRef
        .current()
        .then((v) => {
          if (cancelled) return;
          setData(v);
          setError(null);
          const { pollMs, shouldPoll } = optsRef.current;
          if (pollMs && shouldPoll?.(v)) timer = setTimeout(run, pollMs);
        })
        .catch((e: unknown) => {
          if (!cancelled) setError(e instanceof Error ? e : new Error(String(e)));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    void run();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller controls deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}
