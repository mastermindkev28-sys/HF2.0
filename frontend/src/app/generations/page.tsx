"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Search, Trash2, X, Copy, Layers, Bookmark, FileJson } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import Preview from "@/components/Preview";
import { API, api, fileUrl, fmtDuration, Generation, MODE_LABEL, timeAgo } from "@/lib/api";
import { useEngines } from "@/lib/hooks";
import { useToast } from "@/components/Toast";

export default function GenerationsPage() {
  const toast = useToast();
  const meta = useEngines();
  const [items, setItems] = useState<Generation[]>([]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "saved" | "active" | "failed">("all");
  const [open, setOpen] = useState<Generation | null>(null);
  const [picked, setPicked] = useState<string[]>([]);

  const load = useCallback(() => api<{ generations: Generation[] }>("/api/generations?limit=500").then((r) => setItems(r.generations)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const active = items.some((g) => g.status === "queued" || g.status === "running");
    if (!active) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [items, load]);
  useEffect(() => { if (open) { const fresh = items.find((g) => g.id === open.id); if (fresh && fresh.updated_at !== open.updated_at) setOpen(fresh); } }, [items]); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = useMemo(() => items.filter((g) => {
    if (filter === "saved" && !g.saved) return false;
    if (filter === "active" && !["queued", "running"].includes(g.status)) return false;
    if (filter === "failed" && g.status !== "error") return false;
    return !q || g.prompt.toLowerCase().includes(q.toLowerCase());
  }), [items, q, filter]);

  const engineName = (id: string) => meta?.engines.find((e) => e.id === id)?.name ?? id;
  const del = async (g: Generation) => {
    if (!confirm("Delete this video and its files?")) return;
    try { await api(`/api/generations/${g.id}`, { method: "DELETE" }); setOpen(null); load(); toast("Deleted"); } catch (e: any) { toast(e.message, "err"); }
  };
  const stitch = async () => {
    try { await api("/api/tools/stitch", { method: "POST", json: { sources: picked.map((id) => `generation:${id}`) } }); setPicked([]); load(); toast("Stitching queued"); } catch (e: any) { toast(e.message, "err"); }
  };

  return (
    <div>
      <PageHeader title="My Generations" subtitle={`${items.length} videos, stored on this computer.`}
        right={picked.length > 0 ? (
          <div className="flex items-center gap-2 text-sm"><span className="text-fog-400">{picked.length} selected</span>
            <button className="btn-primary" disabled={picked.length < 2} onClick={stitch}><Layers size={14} /> Stitch in order</button>
            <button className="btn" onClick={() => setPicked([])}>Clear</button></div>
        ) : undefined} />
      <div className="flex flex-wrap items-center gap-3 px-8 pt-6">
        <div className="relative w-80"><Search size={14} className="absolute left-3 top-3 text-fog-500" /><input className="input pl-9" placeholder="Search prompts" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        {(["all", "saved", "active", "failed"] as const).map((f) => <button key={f} className={`chip capitalize ${filter === f ? "chip-on" : ""}`} onClick={() => setFilter(f)}>{f}</button>)}
      </div>
      <div className="grid grid-cols-2 gap-4 p-8 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
        {shown.map((g) => (
          <div key={g.id} className="group panel overflow-hidden transition hover:border-white/20">
            <button className="relative block aspect-video w-full bg-ink-850" onClick={() => setOpen(g)}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {g.thumb_file && <img src={fileUrl("thumbs", g.thumb_file)} alt="" className="h-full w-full object-cover" />}
              {g.status !== "done" && <div className={`absolute inset-0 grid place-items-center text-xs ${g.status === "error" ? "text-red-300" : "text-fog-400"}`}>{g.status === "running" ? `${Math.round(g.progress * 100)}% · ${g.progress_text ?? ""}` : g.status}</div>}
              {g.duration_s ? <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-[10px]">{g.duration_s.toFixed(1)}s</span> : null}
              {g.saved ? <Bookmark size={14} className="absolute left-2 top-2 fill-accent text-accent" /> : null}
            </button>
            <div className="p-3">
              <p className="line-clamp-2 min-h-[2.5em] text-xs leading-snug text-fog-300">{g.prompt || MODE_LABEL[g.mode]}</p>
              <div className="mt-2 flex items-center justify-between text-[10px] text-fog-500">
                <span>{MODE_LABEL[g.mode] ?? g.mode} · {timeAgo(g.created_at)}</span>
                {g.status === "done" && <label className="flex cursor-pointer items-center gap-1" title="Select for stitching"><input type="checkbox" checked={picked.includes(g.id)} onChange={(e) => setPicked((p) => e.target.checked ? [...p, g.id] : p.filter((x) => x !== g.id))} /> stitch</label>}
              </div>
            </div>
          </div>
        ))}
        {shown.length === 0 && <p className="col-span-full text-sm text-fog-500">Nothing here yet. <Link href="/" className="underline">Create something</Link>.</p>}
      </div>

      {open && (
        <div className="fixed inset-0 z-30 flex justify-end bg-black/60 backdrop-blur-sm" onClick={() => setOpen(null)}>
          <div className="h-full w-full max-w-3xl overflow-y-auto border-l border-white/10 bg-ink-950 p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <div className="text-sm text-fog-400">{new Date(open.created_at * 1000).toLocaleString()}</div>
              <button className="btn-ghost" onClick={() => setOpen(null)}><X size={16} /></button>
            </div>
            <Preview gen={open} onNew={() => { load(); toast("Queued. It appears at the top of the list."); }} onUpdate={(g) => { setOpen(g); load(); }} />
            <div className="mt-6 grid grid-cols-[140px_1fr] gap-y-2 text-sm">
              <span className="text-fog-500">Prompt</span><span className="whitespace-pre-wrap text-fog-200">{open.prompt}</span>
              {open.negative_prompt && <><span className="text-fog-500">Negative</span><span className="text-xs text-fog-400">{open.negative_prompt}</span></>}
              <span className="text-fog-500">Model</span><span>{engineName(open.engine)}</span>
              <span className="text-fog-500">Backend</span><span>{open.backend_id}</span>
              {open.params?.width && <><span className="text-fog-500">Output</span><span>{open.params.width}×{open.params.height} · {open.params.frames} frames @ {open.params.fps} fps</span></>}
              {open.params?.steps && <><span className="text-fog-500">Sampling</span><span>{open.params.steps} steps · CFG {open.params.cfg} · seed {open.params.seed}</span></>}
              {open.params?.camera?.length > 0 && <><span className="text-fog-500">Camera</span><span>{open.params.camera.join(", ")}</span></>}
              {open.elapsed_s && <><span className="text-fog-500">Time</span><span>{fmtDuration(open.elapsed_s)}</span></>}
              {open.error && <><span className="text-fog-500">Error</span><span className="text-red-300">{open.error}</span></>}
            </div>
            <div className="mt-6 flex flex-wrap gap-2">
              {["t2v", "i2v", "v2v"].includes(open.mode) && <Link className="btn" href={`/?reuse=${open.id}`}><Copy size={14} /> Reuse settings</Link>}
              <button className="btn" onClick={() => { navigator.clipboard.writeText(open.prompt); toast("Prompt copied"); }}>Copy prompt</button>
              {["t2v", "i2v", "v2v", "extend"].includes(open.mode) && <a className="btn" href={`${API}/api/generations/${open.id}/workflow`} target="_blank" rel="noreferrer"><FileJson size={14} /> ComfyUI workflow</a>}
              <button className="btn ml-auto text-red-300" onClick={() => del(open)}><Trash2 size={14} /> Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
