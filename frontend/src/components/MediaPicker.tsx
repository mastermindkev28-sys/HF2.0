"use client";
import { useEffect, useRef, useState } from "react";
import { ImagePlus, Film, X, Upload } from "lucide-react";
import { api, Asset, fileUrl, Generation, uploadAsset } from "@/lib/api";
import { useToast } from "./Toast";

export interface PickedMedia { ref: string; preview: string; kind: "image" | "video"; label: string }

/** Upload a file or choose one from Assets / My Generations. Returns an input reference the backend understands. */
export default function MediaPicker({ kind, value, onChange }: { kind: "image" | "video"; value: PickedMedia | null; onChange: (m: PickedMedia | null) => void }) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [drag, setDrag] = useState(false);

  const handleFile = async (f: File) => {
    setBusy(true);
    try {
      const a = await uploadAsset(f);
      if (a.kind !== kind) throw new Error(`Please choose ${kind === "image" ? "an image" : "a video"}.`);
      onChange({ ref: `asset:${a.id}`, preview: fileUrl("assets", a.filename), kind: a.kind, label: a.original_name });
    } catch (e: any) {
      toast(e.message, "err");
    } finally {
      setBusy(false);
    }
  };

  if (value) {
    return (
      <div className="relative overflow-hidden rounded-xl border border-white/[0.08] bg-ink-850">
        {value.kind === "image" ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={value.preview} alt="" className="max-h-56 w-full object-contain" />
        ) : (
          <video src={value.preview} className="max-h-56 w-full object-contain" muted loop autoPlay playsInline />
        )}
        <div className="flex items-center justify-between border-t border-white/[0.06] px-3 py-2 text-xs text-fog-400">
          <span className="truncate">{value.label}</span>
          <button className="btn-ghost" onClick={() => onChange(null)}><X size={14} /> Remove</button>
        </div>
      </div>
    );
  }

  const Icon = kind === "image" ? ImagePlus : Film;
  return (
    <>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
        className={`flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-7 text-center transition ${drag ? "border-accent/70 bg-accent/5" : "border-white/10 bg-ink-850"}`}>
        <Icon size={22} strokeWidth={1.5} className="text-fog-500" />
        <div className="text-sm text-fog-300">{busy ? "Uploading…" : `Drop ${kind === "image" ? "an image" : "a video"} here`}</div>
        <div className="flex gap-2">
          <button className="btn text-xs" disabled={busy} onClick={() => inputRef.current?.click()}><Upload size={13} /> Upload</button>
          <button className="btn text-xs" disabled={busy} onClick={() => setOpen(true)}>Choose from library</button>
        </div>
        <input ref={inputRef} type="file" hidden accept={kind === "image" ? "image/*" : "video/*"}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }} />
      </div>
      {open && <LibraryModal kind={kind} onClose={() => setOpen(false)} onPick={(m) => { onChange(m); setOpen(false); }} />}
    </>
  );
}

function LibraryModal({ kind, onClose, onPick }: { kind: "image" | "video"; onClose: () => void; onPick: (m: PickedMedia) => void }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [gens, setGens] = useState<Generation[]>([]);
  useEffect(() => {
    api<{ assets: Asset[] }>(`/api/assets?kind=${kind}`).then((r) => setAssets(r.assets)).catch(() => {});
    if (kind === "video") api<{ generations: Generation[] }>("/api/generations").then((r) => setGens(r.generations.filter((g) => g.status === "done"))).catch(() => {});
  }, [kind]);
  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
      <div className="panel max-h-[80vh] w-full max-w-3xl overflow-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Choose {kind === "image" ? "an image" : "a video"}</h3>
          <button className="btn-ghost" onClick={onClose}><X size={14} /></button>
        </div>
        {assets.length === 0 && gens.length === 0 && <p className="text-sm text-fog-500">Nothing here yet. Upload a file instead.</p>}
        <div className="grid grid-cols-3 gap-3">
          {assets.map((a) => (
            <button key={a.id} className="overflow-hidden rounded-xl border border-white/[0.07] text-left hover:border-accent/60"
              onClick={() => onPick({ ref: `asset:${a.id}`, preview: fileUrl("assets", a.filename), kind: a.kind, label: a.original_name })}>
              {a.kind === "image" ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={fileUrl("assets", a.filename)} alt="" className="aspect-video w-full object-cover" />
              ) : (
                <video src={fileUrl("assets", a.filename)} className="aspect-video w-full object-cover" muted />
              )}
              <div className="truncate px-2 py-1.5 text-xs text-fog-400">{a.original_name}</div>
            </button>
          ))}
          {gens.map((g) => (
            <button key={g.id} className="overflow-hidden rounded-xl border border-white/[0.07] text-left hover:border-accent/60"
              onClick={() => onPick({ ref: `generation:${g.id}`, preview: fileUrl("outputs", g.output_file!), kind: "video", label: g.prompt.slice(0, 40) })}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {g.thumb_file ? <img src={fileUrl("thumbs", g.thumb_file)} alt="" className="aspect-video w-full object-cover" /> : <div className="aspect-video bg-ink-800" />}
              <div className="truncate px-2 py-1.5 text-xs text-fog-400">{g.prompt}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
