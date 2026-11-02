"use client";
import { useCallback, useEffect, useState } from "react";
import { Cpu, HardDrive, Download, Trash2, ExternalLink, Check, Lock, MonitorSmartphone } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { api, EngineInfo } from "@/lib/api";
import { useBackendStatus, useEngines, useSettings } from "@/lib/hooks";
import { useToast } from "@/components/Toast";

const MODE_SHORT: Record<string, string> = { t2v: "Text→Video", i2v: "Image→Video", v2v: "Video→Video" };

export default function ModelsPage() {
  const toast = useToast();
  const meta = useEngines();
  const { settings } = useSettings();
  const [backendId, setBackendId] = useState("");
  useEffect(() => { if (settings && !backendId) setBackendId(settings.active_backend); }, [settings, backendId]);
  const { status, reload } = useBackendStatus(backendId, 15000);
  const [hw, setHw] = useState<any>(null);
  const [downloads, setDownloads] = useState<any[]>([]);
  useEffect(() => { api("/api/hardware").then(setHw).catch(() => {}); }, []);

  const pollDownloads = useCallback(async () => {
    if (!backendId || !status?.online || !status.bridge) return;
    try { setDownloads((await api<{ downloads: any[] }>(`/api/models/downloads?backend_id=${backendId}`)).downloads); } catch {}
  }, [backendId, status?.online, status?.bridge]);
  useEffect(() => {
    pollDownloads();
    const running = downloads.some((d) => d.status === "running");
    const t = setInterval(() => { pollDownloads(); if (running) reload(); }, running ? 2000 : 10000);
    return () => clearInterval(t);
  }, [pollDownloads, downloads, reload]);

  const install = async (id: string) => {
    const eng = meta?.engines.find((e) => e.id === id);
    if (eng && !eng.runs_on_cpu && status?.online && !gpu) {
      if (!confirm(`${status.name} has no GPU. ${eng.name} would take hours per clip there.\n\nInstall it on your Kaggle GPU backend instead (pick it at the top right). Install here anyway?`)) return;
    }
    try {
      const r = await api<{ started: string[] }>("/api/models/install", { method: "POST", json: { engine_id: id, backend_id: backendId } });
      toast(r.started.length ? `Downloading ${r.started.length} file(s) on ${status?.name}` : "Already installed");
      pollDownloads();
    } catch (e: any) { toast(e.message, "err"); }
  };
  const remove = async (id: string, name: string) => {
    if (!confirm(`Delete ${name}'s model files from ${status?.name}?`)) return;
    try { const r = await api<{ removed: string[] }>("/api/models/remove", { method: "POST", json: { engine_id: id, backend_id: backendId } }); toast(`Removed ${r.removed.length} file(s)`); reload(); } catch (e: any) { toast(e.message, "err"); }
  };

  const gpu = status?.bridge?.gpu;
  return (
    <div>
      <PageHeader title="Explore Models" subtitle="Open-weight video models only. No paid APIs, no credits. Models are downloaded to the backend that runs them."
        right={<select className="input w-64" value={backendId} onChange={(e) => setBackendId(e.target.value)}>{settings?.backends.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select>} />
      <div className="grid gap-4 p-8 lg:grid-cols-2">
        <div className="panel p-5">
          <div className="label mb-3 flex items-center gap-2"><MonitorSmartphone size={12} /> This computer</div>
          {hw ? (
            <>
              <div className="grid grid-cols-2 gap-y-1.5 text-sm">
                <span className="text-fog-500">System</span><span>{hw.os} · {hw.arch}</span>
                <span className="text-fog-500">CPU</span><span>{hw.cores} cores / {hw.threads} threads</span>
                <span className="text-fog-500">Memory</span><span>{hw.ram_gb} GB</span>
                <span className="text-fog-500">Graphics</span><span>{hw.gpus.map((g: any) => g.name).join(", ") || "—"}</span>
                <span className="text-fog-500">Free disk</span><span>{hw.disk_free_gb} GB</span>
              </div>
              <p className="mt-4 rounded-xl bg-ink-850 p-3 text-xs leading-relaxed text-fog-300">{hw.verdict}</p>
            </>
          ) : <p className="text-sm text-fog-500">Detecting…</p>}
        </div>
        <div className="panel p-5">
          <div className="label mb-3 flex items-center gap-2"><Cpu size={12} /> Backend · {status?.name ?? "…"}</div>
          {status?.online ? (
            <div className="grid grid-cols-2 gap-y-1.5 text-sm">
              <span className="text-fog-500">Status</span><span className="text-accent">Online</span>
              <span className="text-fog-500">GPU</span><span>{gpu ? `${gpu.name}${gpu.vram_total_gb ? ` · ${gpu.vram_total_gb} GB` : ""}` : "None (CPU)"}</span>
              {gpu?.vram_total_gb && <><span className="text-fog-500">VRAM in use</span><span>{gpu.vram_used_gb} GB</span></>}
              {status.bridge?.ram_total_gb && <><span className="text-fog-500">RAM in use</span><span>{status.bridge.ram_used_gb} / {status.bridge.ram_total_gb} GB</span></>}
              {status.bridge?.disk_free_gb && <><span className="text-fog-500">Free disk</span><span>{status.bridge.disk_free_gb} GB</span></>}
              <span className="text-fog-500">Queue</span><span>{status.queue?.running ?? 0} running · {status.queue?.pending ?? 0} waiting</span>
              {!status.bridge && <p className="col-span-2 mt-2 text-xs text-amber-300/90">The HIGGS bridge node isn&apos;t installed on this backend, so models can&apos;t be managed from here.</p>}
              {status.nodes_ok === false && <p className="col-span-2 mt-2 text-xs text-amber-300/90">This ComfyUI is too old for Wan 2.2 / LTX video nodes. Update it.</p>}
            </div>
          ) : <p className="text-sm text-red-300/90">{status?.error ?? "Checking…"}</p>}
        </div>
      </div>

      <div className="grid gap-4 px-8 pb-10 lg:grid-cols-2">
        {meta?.engines.map((e) => <EngineCard key={e.id} e={e} st={status?.engines?.[e.id]} online={!!status?.online} canManage={!!status?.bridge} downloads={downloads} onInstall={() => install(e.id)} onRemove={() => remove(e.id, e.name)} gpuVram={gpu?.vram_total_gb} />)}
        {meta?.upscaler && (
          <div className="panel p-5">
            <div className="flex items-center justify-between"><h3 className="font-medium">Real-ESRGAN ×2 upscaler</h3>{status?.upscaler_installed ? <span className="badge border-accent/30 text-accent"><Check size={10} /> Installed</span> : <span className="badge">Not installed</span>}</div>
            <p className="mt-2 text-sm text-fog-400">AI upscaling for finished clips (Enhance → AI upscale). BSD-3 license. {meta.upscaler.size_gb * 1000} MB.</p>
            {status?.online && status.bridge && !status.upscaler_installed && <button className="btn mt-4" onClick={() => install("upscaler")}><Download size={14} /> Install</button>}
          </div>
        )}
      </div>
    </div>
  );
}

function EngineCard({ e, st, online, canManage, downloads, onInstall, onRemove, gpuVram }: { e: EngineInfo; st?: { installed: boolean; missing: string[] }; online: boolean; canManage: boolean; downloads: any[]; onInstall: () => void; onRemove: () => void; gpuVram?: number }) {
  const mine = downloads.filter((d) => e.files.some((f) => d.key === `${f.folder}/${f.filename}`) && d.status !== "done");
  const busy = mine.some((d) => d.status === "running");
  const tooSmall = gpuVram !== undefined && gpuVram > 0 && gpuVram < e.min_vram_gb;
  return (
    <div className={`panel p-5 ${e.catalog_only ? "opacity-70" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.14em] text-fog-500">{e.family}</div>
          <h3 className="mt-0.5 text-lg font-medium">{e.name}</h3>
        </div>
        {e.catalog_only ? <span className="badge"><Lock size={10} /> Needs bigger GPU</span>
          : !online ? <span className="badge">Backend offline</span>
          : st?.installed ? <span className="badge border-accent/30 text-accent"><Check size={10} /> Installed</span>
          : <span className="badge">Not installed</span>}
      </div>
      <p className="mt-3 text-sm leading-relaxed text-fog-400">{e.description}</p>
      <div className="mt-4 flex flex-wrap gap-1.5">{e.modes.map((m) => <span key={m} className="badge">{MODE_SHORT[m]}</span>)}</div>
      <div className="mt-4 grid grid-cols-2 gap-y-1 text-xs">
        <span className="text-fog-500">GPU memory</span><span>{e.min_vram_gb} GB min · {e.recommended_vram_gb} GB recommended</span>
        <span className="text-fog-500">CPU only</span><span>{e.cpu_note}</span>
        {!e.catalog_only && <><span className="text-fog-500">Download</span><span className="flex items-center gap-1"><HardDrive size={11} /> {e.total_size_gb} GB</span></>}
        <span className="text-fog-500">License</span><span>{e.license}</span>
      </div>
      {tooSmall && !e.catalog_only && <p className="mt-3 text-xs text-amber-300/90">This backend&apos;s GPU has {gpuVram} GB; this model wants at least {e.min_vram_gb} GB.</p>}
      {mine.length > 0 && (
        <div className="mt-4 flex flex-col gap-2">
          {mine.map((d) => (
            <div key={d.key} className="text-xs">
              <div className="flex justify-between text-fog-400"><span className="truncate">{d.key.split("/")[1]}</span><span>{d.status === "error" ? <span className="text-red-300">{d.error}</span> : d.total ? `${Math.round((100 * d.done) / d.total)}% · ${d.speed_mb_s ?? 0} MB/s` : "starting…"}</span></div>
              <div className="mt-1 h-1 overflow-hidden rounded bg-ink-700"><div className="h-full bg-accent" style={{ width: `${d.total ? (100 * d.done) / d.total : 2}%` }} /></div>
            </div>
          ))}
        </div>
      )}
      <div className="mt-5 flex items-center gap-2">
        {!e.catalog_only && online && canManage && !st?.installed && !busy && <button className="btn-primary" onClick={onInstall}><Download size={14} /> {mine.length ? "Retry install" : "Install on this backend"}</button>}
        {!e.catalog_only && online && canManage && st?.installed && <button className="btn" onClick={onRemove}><Trash2 size={14} /> Remove</button>}
        <a className="btn-ghost ml-auto" href={e.homepage} target="_blank" rel="noreferrer">Model page <ExternalLink size={12} /></a>
      </div>
      {!e.catalog_only && st && !st.installed && st.missing.length > 0 && <p className="mt-3 text-[11px] text-fog-500">Missing: {st.missing.join(", ")}</p>}
    </div>
  );
}
