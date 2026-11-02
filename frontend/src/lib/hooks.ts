"use client";
import { useCallback, useEffect, useState } from "react";
import { api, BackendStatus, CameraMove, EngineInfo, Settings } from "./api";

export function useEngines() {
  const [data, setData] = useState<{ engines: EngineInfo[]; camera_moves: CameraMove[]; upscaler: any } | null>(null);
  useEffect(() => { api("/api/engines").then(setData).catch(() => {}); }, []);
  return data;
}

export function useSettings() {
  const [s, setS] = useState<Settings | null>(null);
  const reload = useCallback(() => api<Settings>("/api/settings").then(setS).catch(() => {}), []);
  useEffect(() => { reload(); }, [reload]);
  return { settings: s, reload, setSettings: setS };
}

export function useBackendStatus(backendId?: string, intervalMs = 20000) {
  const [st, setSt] = useState<BackendStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!backendId) return;
    setLoading(true);
    try {
      const r = await api<{ backends: BackendStatus[] }>(`/api/backends/status?backend_id=${backendId}`);
      setSt(r.backends[0] ?? null);
    } catch { setSt(null); } finally { setLoading(false); }
  }, [backendId]);
  useEffect(() => {
    reload();
    const t = setInterval(reload, intervalMs);
    return () => clearInterval(t);
  }, [reload, intervalMs]);
  return { status: st, loading, reload };
}
