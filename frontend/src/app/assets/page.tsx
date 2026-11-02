"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Upload, Trash2 } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { api, Asset, fileUrl, timeAgo, uploadAsset } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function AssetsPage() {
  const toast = useToast();
  const [items, setItems] = useState<Asset[]>([]);
  const [kind, setKind] = useState<"" | "image" | "video">("");
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const load = useCallback(() => api<{ assets: Asset[] }>(`/api/assets${kind ? `?kind=${kind}` : ""}`).then((r) => setItems(r.assets)).catch(() => {}), [kind]);
  useEffect(() => { load(); }, [load]);

  const upload = async (files: FileList | null) => {
    if (!files) return;
    setBusy(true);
    for (const f of Array.from(files)) { try { await uploadAsset(f); } catch (e: any) { toast(`${f.name}: ${e.message}`, "err"); } }
    setBusy(false);
    load();
  };
  const del = async (a: Asset) => {
    if (!confirm(`Delete ${a.original_name}?`)) return;
    await api(`/api/assets/${a.id}`, { method: "DELETE" });
    load();
  };

  return (
    <div>
      <PageHeader title="Assets" subtitle="Images and videos you've uploaded for Image to Video and Video to Video. Stored on this computer."
        right={<><button className="btn-primary" disabled={busy} onClick={() => ref.current?.click()}><Upload size={15} /> {busy ? "Uploading…" : "Upload"}</button><input ref={ref} type="file" multiple hidden accept="image/*,video/*" onChange={(e) => { upload(e.target.files); e.target.value = ""; }} /></>} />
      <div className="flex gap-2 px-8 pt-6">
        {([["", "All"], ["image", "Images"], ["video", "Videos"]] as const).map(([k, l]) => <button key={k} className={`chip ${kind === k ? "chip-on" : ""}`} onClick={() => setKind(k)}>{l}</button>)}
      </div>
      <div className="grid grid-cols-2 gap-4 p-8 md:grid-cols-4 xl:grid-cols-6"
        onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files); }}>
        {items.map((a) => (
          <div key={a.id} className="group panel overflow-hidden">
            <div className="relative aspect-square bg-ink-850">
              {a.kind === "image" ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={fileUrl("assets", a.filename)} alt="" className="h-full w-full object-cover" />
              ) : (
                <video src={fileUrl("assets", a.filename)} className="h-full w-full object-cover" muted loop onMouseEnter={(e) => e.currentTarget.play()} onMouseLeave={(e) => e.currentTarget.pause()} />
              )}
              <button className="absolute right-2 top-2 hidden rounded-lg bg-black/70 p-1.5 text-red-300 group-hover:block" onClick={() => del(a)}><Trash2 size={13} /></button>
            </div>
            <div className="p-2.5">
              <div className="truncate text-xs text-fog-300">{a.original_name}</div>
              <div className="mt-0.5 text-[10px] text-fog-500">{a.width ? `${a.width}×${a.height} · ` : ""}{a.duration_s ? `${a.duration_s.toFixed(1)}s · ` : ""}{timeAgo(a.created_at)}</div>
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="col-span-full text-sm text-fog-500">Drop images or videos here.</p>}
      </div>
    </div>
  );
}
