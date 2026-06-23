import { useCallback, useEffect, useState } from "react";
import { api } from "./client";
import type {
  ColumnsResponse,
  ModelsResponse,
  PortsResponse,
  ProjectStatus,
  ReleasesResponse,
} from "./types";

// ---------------------------------------------------------------------------
// Generic async-resource hook: fetches on mount + when `deps` change, exposes
// { data, error, loading, reload }. Reads are cheap and the dataset is bounded,
// so we refetch wholesale rather than caching — simplicity over a query lib.
// ---------------------------------------------------------------------------
export interface Resource<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useResource<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  enabled = true,
): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    fetcher()
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e) => {
        if (alive) setError(e?.detail ?? String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled]);

  return { data, error, loading, reload };
}

// ---------------------------------------------------------------------------
// Typed resource wrappers
// ---------------------------------------------------------------------------
export const useStatus = () =>
  useResource<ProjectStatus>(() => api.get("/project/status"), []);

export const useModels = (open: boolean) =>
  useResource<ModelsResponse>(
    () => api.get("/models"),
    [],
    open,
  );

export const useColumns = (open: boolean) =>
  useResource<ColumnsResponse>(() => api.get("/columns"), [], open);

export const useReleases = (open: boolean) =>
  useResource<ReleasesResponse>(() => api.get("/releases"), [], open);

export const usePorts = (modelId: number | null) =>
  useResource<PortsResponse>(
    () => api.get(`/models/${modelId}/ports?limit=5000`),
    [modelId],
    modelId !== null,
  );
