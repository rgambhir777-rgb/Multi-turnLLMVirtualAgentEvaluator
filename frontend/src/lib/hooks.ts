import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

export interface Resource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (value: T) => void;
}

/** Fetch a GET endpoint, with optional polling while `poll(data)` returns true. */
export function useApi<T>(path: string | null, options: { poll?: (data: T) => boolean; intervalMs?: number } = {}): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(path));
  const pollRef = useRef(options.poll);
  pollRef.current = options.poll;

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const result = await api.get<T>(path);
      setData(result);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setLoading(Boolean(path));
    void load();
  }, [load, path]);

  useEffect(() => {
    if (!data || !pollRef.current || !pollRef.current(data)) return;
    const timer = window.setTimeout(() => void load(), options.intervalMs ?? 1500);
    return () => window.clearTimeout(timer);
  }, [data, load, options.intervalMs]);

  return { data, error, loading, reload: load, setData };
}
