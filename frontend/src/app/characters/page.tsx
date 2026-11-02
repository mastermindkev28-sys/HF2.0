"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Plus, Trash2, X, ImagePlus, Info } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { api, Character, fileUrl } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function CharactersPage() {
  const toast = useToast();
  const [items, setItems] = useState<Character[]>([]);
  const [editing, setEditing] = useState<Character | "new" | null>(null);
  const load = useCallback(() => api<{ characters: Character[] }>("/api/characters").then((r) => setItems(r.characters)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <PageHeader title="Characters" subtitle="Save a person, mascot or product once and reuse it across generations."
        right={<button className="btn-primary" onClick={() => setEditing("new")}><Plus size={15} /> New character</button>} />
      <div className="mx-8 mt-6 flex gap-3 rounded-xl border border-white/[0.06] bg-ink-900 p-4 text-xs leading-relaxed text-fog-400">
        <Info size={15} className="mt-0.5 shrink-0 text-fog-500" />
        <p>How consistency works with the models available to you: in <b className="text-fog-200">Image to Video</b>, the character&apos;s first reference image becomes the starting frame, so face, clothing and build carry over strongly. In <b className="text-fog-200">Text to Video</b>, the written description is added to your prompt, which keeps the character similar but not identical. Neither Wan 2.2 5B nor LTX 2B has a dedicated identity adapter, so the studio doesn&apos;t claim one.</p>
      </div>
      <div className="grid grid-cols-2 gap-4 p-8 md:grid-cols-3 xl:grid-cols-5">
        {items.map((c) => (
          <button key={c.id} className="panel overflow-hidden text-left transition hover:border-white/20" onClick={() => setEditing(c)}>
            <div className="aspect-[4/5] bg-ink-850">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {c.images[0] && <img src={fileUrl("characters", `${c.id}/${c.images[0]}`)} alt="" className="h-full w-full object-cover" />}
            </div>
            <div className="p-3">
              <div className="text-sm font-medium">{c.name}</div>
              <div className="mt-1 line-clamp-2 text-xs text-fog-500">{c.description || "No description"}</div>
              <div className="mt-2 text-[10px] text-fog-500">{c.images.length} reference image{c.images.length === 1 ? "" : "s"}</div>
            </div>
          </button>
        ))}
        {items.length === 0 && <p className="col-span-full text-sm text-fog-500">No characters yet. Create one from reference photos, or use “Save character” on any generated video.</p>}
      </div>
      {editing && <Editor ch={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); toast("Character saved"); }} onDeleted={() => { setEditing(null); load(); toast("Character deleted"); }} />}
    </div>
  );
}

function Editor({ ch, onClose, onSaved, onDeleted }: { ch: Character | null; onClose: () => void; onSaved: () => void; onDeleted: () => void }) {
  const toast = useToast();
  const [name, setName] = useState(ch?.name ?? "");
  const [desc, setDesc] = useState(ch?.description ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const [images, setImages] = useState<string[]>(ch?.images ?? []);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  const save = async () => {
    if (!name.trim()) return toast("Give the character a name", "err");
    setBusy(true);
    const fd = new FormData();
    fd.append("name", name);
    fd.append("description", desc);
    files.forEach((f) => fd.append("files", f));
    try {
      await api(ch ? `/api/characters/${ch.id}` : "/api/characters", { method: ch ? "PUT" : "POST", body: fd });
      onSaved();
    } catch (e: any) { toast(e.message, "err"); } finally { setBusy(false); }
  };
  const removeImage = async (img: string) => {
    if (!ch) return;
    const r = await api<Character>(`/api/characters/${ch.id}/images/${img}`, { method: "DELETE" });
    setImages(r.images);
  };
  const del = async () => {
    if (!ch || !confirm(`Delete ${ch.name}?`)) return;
    await api(`/api/characters/${ch.id}`, { method: "DELETE" });
    onDeleted();
  };

  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
      <div className="panel w-full max-w-xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-5 flex items-center justify-between"><h3 className="font-display text-xl">{ch ? "Edit character" : "New character"}</h3><button className="btn-ghost" onClick={onClose}><X size={16} /></button></div>
        <div className="flex flex-col gap-4">
          <div><div className="label mb-2">Name</div><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Maya" /></div>
          <div><div className="label mb-2">Appearance description</div>
            <textarea className="input min-h-[100px]" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="A woman in her late 20s with short silver hair, green eyes, freckles, wearing a black leather jacket over a white t-shirt" />
            <p className="mt-1.5 text-[11px] text-fog-500">Be specific about face, hair, clothing and build. This text is added to every prompt that uses the character.</p></div>
          <div>
            <div className="label mb-2">Reference images</div>
            <div className="flex flex-wrap gap-2">
              {images.map((i) => (
                <div key={i} className="group relative h-20 w-20 overflow-hidden rounded-lg">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={fileUrl("characters", `${ch!.id}/${i}`)} alt="" className="h-full w-full object-cover" />
                  <button className="absolute right-1 top-1 hidden rounded bg-black/70 p-0.5 group-hover:block" onClick={() => removeImage(i)}><X size={12} /></button>
                </div>
              ))}
              {files.map((f, i) => (
                <div key={i} className="relative h-20 w-20 overflow-hidden rounded-lg ring-1 ring-accent/50">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={URL.createObjectURL(f)} alt="" className="h-full w-full object-cover" />
                </div>
              ))}
              <button className="grid h-20 w-20 place-items-center rounded-lg border border-dashed border-white/15 text-fog-500 hover:border-white/30" onClick={() => ref.current?.click()}><ImagePlus size={18} /></button>
              <input ref={ref} type="file" accept="image/*" multiple hidden onChange={(e) => { setFiles((f) => [...f, ...Array.from(e.target.files ?? [])]); e.target.value = ""; }} />
            </div>
            <p className="mt-1.5 text-[11px] text-fog-500">The first image is used as the starting frame in Image to Video. A clear, well-lit, front-facing shot works best.</p>
          </div>
        </div>
        <div className="mt-6 flex items-center gap-2">
          {ch && <button className="btn text-red-300" onClick={del}><Trash2 size={14} /> Delete</button>}
          {ch && <Link className="btn" href="/">Use in Create</Link>}
          <button className="btn-primary ml-auto" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>
  );
}
