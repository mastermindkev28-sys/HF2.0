"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, BackendStatus } from "@/lib/api";

export default function BackendPill() {
  const [st, setSt] = useState<BackendStatus | null>(null);
  const [active, setActive] = useState<string>("");
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const s = await api<{ active: string }>("/api/settings").then((x: any) => x.active_backend);
        const r = await api<{ backends: BackendStatus[] }>(`/api/backends/status?backend_id=${s}`);
        if (alive) { setActive(s); setSt(r.backends[0] ?? null); }
      } catch { if (alive) setSt(null); }
    };
    load();
    const t = setInterval(load, 15000);
    const onChange = () => load();
    window.addEventListener("higgs:settings", onChange);
    return () => { alive = false; clearInterval(t); window.removeEventListener("higgs:settings", onChange); };
  }, []);
  const gpu = st?.bridge?.gpu?.name ?? st?.devices?.[0]?.name;
  return (
    <Link href="/settings/" className="block rounded-xl border border-white/[0.06] bg-ink-900 p-3 text-xs transition hover:border-white/15">
      <div className="mb-1 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${st?.online ? "bg-accent shadow-[0_0_8px_#d8ff5c]" : "bg-red-500/80"}`} />
        <span className="font-medium text-fog-100">{st?.name ?? (active || "Backend")}</span>
      </div>
      <div className="truncate text-fog-500">
        {st?.online ? (gpu ? String(gpu).replace(/^cuda:\d+\s*/, "") : "Online") : st?.error ?? "Checking…"}
      </div>
      {st?.online && st.bridge?.gpu?.vram_total_gb && (
        <div className="mt-2">
          <div className="h-1 overflow-hidden rounded bg-ink-700">
            <div className="h-full bg-accent/70" style={{ width: `${(100 * st.bridge.gpu.vram_used_gb) / st.bridge.gpu.vram_total_gb}%` }} />
          </div>
          <div className="mt-1 text-[10px] text-fog-500">VRAM {st.bridge.gpu.vram_used_gb} / {st.bridge.gpu.vram_total_gb} GB</div>
        </div>
      )}
    </Link>
  );
}
