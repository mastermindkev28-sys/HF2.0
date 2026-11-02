"use client";
import { useState } from "react";
import { Download, RefreshCw, Shuffle, FastForward, Bookmark, BookmarkCheck, UserPlus, Sparkles, Gauge, X, Loader2, AlertTriangle } from "lucide-react";
import { api, fileUrl, fmtDuration, Generation, MODE_LABEL } from "@/lib/api";
import { useToast } from "./Toast";

export default function Preview({ gen, onNew, onUpdate, aspect = "16:9" }: {
  gen: Generation | null; onNew: (g: Generation) => void; onUpdate?: (g: Generation) => void; aspect?: string;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const ar = gen?.params?.width && gen?.params?.height ? `${gen.params.width}/${gen.params.height}` : aspect.replace(":", "/");

  const act = async (key: string, fn: () => Promise<any>, msg?: string) => {
    setBusy(key);
    try { const r = await fn(); if (msg) toast(msg); return r; } catch (e: any) { toast(e.message, "err"); } finally { setBusy(null); }
  };

  const isGen = gen && ["t2v", "i2v", "v2v", "extend"].includes(gen.mode);
  return (
    <div className="flex flex-col gap-3">
      <div className="panel relative grid place-items-center overflow-hidden bg-ink-950" style={{ aspectRatio: ar, maxHeight: "62vh" }}>
        {!gen && (
          <div className="px-8 text-center">
            <div className="font-display text-2xl text-fog-300">Your next shot appears here</div>
            <p className="mt-2 text-sm text-fog-500">Describe a scene, pick a camera move, and generate.</p>
          </div>
        )}
        {gen && gen.status === "done" && gen.output_file && (
          <video key={gen.output_file} src={fileUrl("outputs", gen.output_file)} controls autoPlay loop playsInline className="h-full w-full bg-black object-contain" />
        )}
        {gen && (gen.status === "queued" || gen.status === "running") && (
          <div className="flex w-2/3 max-w-md flex-col items-center gap-4">
            {gen.thumb_file && /* eslint-disable-next-line @next/next/no-img-element */ <img src={fileUrl("thumbs", gen.thumb_file)} alt="" className="absolute inset-0 h-full w-full object-cover opacity-10 blur-xl" />}
            <Loader2 className="animate-spin text-accent" size={26} />
            <div className="text-sm text-fog-300">{gen.status === "queued" ? "Waiting in queue…" : gen.progress_text || "Working…"}</div>
            <div className="h-1 w-full overflow-hidden rounded bg-ink-700">
              <div className="h-full bg-accent transition-all duration-700" style={{ width: `${Math.max(2, gen.progress * 100)}%` }} />
            </div>
            <div className="text-xs text-fog-500">{Math.round(gen.progress * 100)}% · started {fmtDuration(Date.now() / 1000 - gen.created_at)} ago</div>
            <button className="btn-ghost relative" onClick={() => act("cancel", () => api(`/api/generations/${gen.id}/cancel`, { method: "POST" }), "Cancelling…")}><X size={13} /> Cancel</button>
          </div>
        )}
        {gen && gen.status === "error" && (
          <div className="max-w-lg px-8 text-center">
            <AlertTriangle className="mx-auto mb-3 text-red-400" size={24} />
            <div className="text-sm font-medium text-red-200">Generation failed</div>
            <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-fog-400">{gen.error}</p>
          </div>
        )}
        {gen && gen.status === "cancelled" && <div className="text-sm text-fog-500">Cancelled</div>}
      </div>

      {gen && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 text-xs text-fog-500">
            <span className="badge mr-2">{MODE_LABEL[gen.mode] ?? gen.mode}</span>
            {gen.params?.width && <span>{gen.params.width}×{gen.params.height} · {gen.params.fps} fps · seed {gen.params.seed}</span>}
            {gen.elapsed_s ? <span> · took {fmtDuration(gen.elapsed_s)}</span> : null}
          </div>
          {gen.status === "done" && gen.output_file && (
            <div className="flex flex-wrap gap-1">
              <a className="btn-ghost" href={fileUrl("outputs", gen.output_file)} download={`higgs-${gen.id}.mp4`}><Download size={13} /> Download</a>
              {isGen && gen.mode !== "extend" && <>
                <button className="btn-ghost" disabled={!!busy} onClick={() => act("regen", () => api(`/api/generations/${gen.id}/regenerate`, { method: "POST", json: { variation: false } }).then(onNew), "Regenerating with the same seed")}><RefreshCw size={13} /> Regenerate</button>
                <button className="btn-ghost" disabled={!!busy} onClick={() => act("var", () => api(`/api/generations/${gen.id}/regenerate`, { method: "POST", json: { variation: true } }).then(onNew), "Variation queued")}><Shuffle size={13} /> Variation</button>
              </>}
              {isGen && <button className="btn-ghost" disabled={!!busy} title="Continues from the last frame with image-to-video, then joins the clips" onClick={() => act("ext", () => api(`/api/generations/${gen.id}/extend`, { method: "POST", json: {} }).then(onNew), "Extension queued")}><FastForward size={13} /> Extend</button>}
              <button className="btn-ghost" disabled={!!busy} onClick={() => act("save", () => api<Generation>(`/api/generations/${gen.id}/saved`, { method: "POST", json: { saved: !gen.saved } }).then((g) => onUpdate?.(g)), gen.saved ? "Removed from saved" : "Saved to library")}>
                {gen.saved ? <BookmarkCheck size={13} className="text-accent" /> : <Bookmark size={13} />} {gen.saved ? "Saved" : "Save"}
              </button>
              {isGen && <button className="btn-ghost" disabled={!!busy} onClick={() => { const name = prompt("Character name?"); if (name) act("char", () => api("/api/characters/from-generation", { method: "POST", json: { generation_id: gen.id, name } }), `Saved “${name}” to Characters`); }}><UserPlus size={13} /> Save character</button>}
              <ToolsMenu gen={gen} onNew={onNew} act={act} busy={!!busy} />
            </div>
          )}
        </div>
      )}
      {gen?.final_prompt && gen.mode !== "stitch" && (
        <details className="text-xs text-fog-500">
          <summary className="cursor-pointer select-none hover:text-fog-300">Prompt sent to the model</summary>
          <p className="mt-2 rounded-lg bg-ink-900 p-3 leading-relaxed text-fog-400">{gen.final_prompt}</p>
        </details>
      )}
    </div>
  );
}

function ToolsMenu({ gen, onNew, act, busy }: { gen: Generation; onNew: (g: Generation) => void; act: any; busy: boolean }) {
  const [open, setOpen] = useState(false);
  const run = (tool: string, body: any, msg: string) => { setOpen(false); act(tool, () => api(`/api/tools/${tool}`, { method: "POST", json: { source: `generation:${gen.id}`, ...body } }).then(onNew), msg); };
  return (
    <div className="relative">
      <button className="btn-ghost" disabled={busy} onClick={() => setOpen(!open)}><Sparkles size={13} /> Enhance</button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-64 rounded-xl border border-white/10 bg-ink-800 p-1 text-xs shadow-2xl">
          <MenuItem title="AI upscale ×2" sub="Real-ESRGAN on the backend" onClick={() => run("upscale_ai", {}, "AI upscale queued")} />
          <MenuItem title="Quick upscale ×2" sub="FFmpeg Lanczos, on this computer" onClick={() => run("upscale_basic", { factor: 2 }, "Upscale queued")} />
          <MenuItem title="Smooth to 48 fps" sub="FFmpeg motion interpolation (not AI)" icon={<Gauge size={12} />} onClick={() => run("interpolate", { target_fps: 48 }, "Interpolation queued")} />
        </div>
      )}
    </div>
  );
}

function MenuItem({ title, sub, onClick, icon }: { title: string; sub: string; onClick: () => void; icon?: React.ReactNode }) {
  return (
    <button onClick={onClick} className="flex w-full flex-col items-start rounded-lg px-3 py-2 text-left hover:bg-white/5">
      <span className="flex items-center gap-1.5 text-fog-100">{icon}{title}</span>
      <span className="text-fog-500">{sub}</span>
    </button>
  );
}
