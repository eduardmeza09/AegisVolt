import { useCallback, useEffect, useRef, useState } from "react";
import { gql } from "./api";

/** Polling de una query GraphQL ("tiempo real"). Se pausa con la pestaña oculta. */
export function usePoll<T>(query: string, intervalMs: number, variables?: Record<string, unknown>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const vars = JSON.stringify(variables ?? {});
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const d = await gql<T>(query, JSON.parse(vars));
      if (!alive.current) return;
      setData(d);
      setError(null);
      setUpdatedAt(Date.now());
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    }
  }, [query, vars]);

  useEffect(() => {
    alive.current = true;
    refresh();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, intervalMs);
    return () => {
      alive.current = false;
      window.clearInterval(id);
    };
  }, [refresh, intervalMs]);

  return { data, error, updatedAt, refresh };
}

export function useLocalStorage(key: string, initial: string): [string, (v: string) => void] {
  const [value, setValue] = useState(() => {
    try {
      return window.localStorage.getItem(key) ?? initial;
    } catch {
      return initial;
    }
  });
  const set = (v: string) => {
    setValue(v);
    try {
      window.localStorage.setItem(key, v);
    } catch {
      /* almacenamiento no disponible */
    }
  };
  return [value, set];
}
