"use client";
import { useEffect, useState } from "react";
import { Plus, Trash2, PlugZap, Check } from "lucide-react";
import PageHeader from "@/components/PageHeader";
import { api, Backend, BackendStatus, Settings } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function SettingsPage() {
  const toast = useToast();
  const [s, setS] = useState<Settings | null>(null);
  const [tests, setTests] = useState<Record<string, BackendStatus | "testing">>({});
  const [ollama, setOllama] = useState<string[]>([]);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    api<Settings>("/api/settings").then(setS);
    api<{ models: string[] }>("/api/ollama/models").then((r) => setOllama(r.models)).catch(() => {});
    api("/api/health").then(setHealth).catch(() => {});
  }, []);

  if (!s) return null;
  const setBackend = (i: number, patch: Partial<Backend>) => setS({ ...s, backends: s.backends.map((b, j) => (j === i ? { ...b, ...patch } : b)) });

  const save = async () => {
    try {
      const r = await api<Settings>("/api/settings", { method: "PUT", json: s });
      setS(r);
      window.dispatchEvent(new Event("higgs:settings"));
      toast("Settings saved");
    } catch (e: any) { toast(e.message, "err"); }
  };
  const test = async (b: Backend) => {
    setTests((t) => ({ ...t, [b.id]: "testing" }));
    try { const r = await api<BackendStatus>("/api/backends/test", { method: "POST", json: { url: b.url, token: b.token } }); setTests((t) => ({ ...t, [b.id]: r })); }
    catch (e: any) { setTests((t) => ({ ...t, [b.id]: { online: false, error: e.message } as BackendStatus })); }
  };

  return (
    <div>
      <PageHeader title="Settings" subtitle="Where videos are generated, and a few local tools." right={<button className="btn-primary" onClick={save}>Save changes</button>} />
      <div className="flex max-w-4xl flex-col gap-8 p-8">
        <section>
          <h2 className="mb-1 text-sm font-semibold">Generation backends</h2>
          <p className="mb-4 text-xs text-fog-500">Each backend is a ComfyUI server. Pick which one Create uses by default. The Kaggle address changes every time you start the notebook: paste the new one here.</p>
          <div className="flex flex-col gap-3">
            {s.backends.map((b, i) => {
              const t = tests[b.id];
              return (
                <div key={b.id} className={`panel p-4 ${s.active_backend === b.id ? "border-accent/40" : ""}`}>
                  <div className="flex items-center gap-3">
                    <input type="radio" checked={s.active_backend === b.id} onChange={() => setS({ ...s, active_backend: b.id })} />
                    <input className="input max-w-xs" value={b.name} onChange={(e) => setBackend(i, { name: e.target.value })} />
                    {s.active_backend === b.id && <span className="badge border-accent/30 text-accent">Default</span>}
                    {!["local", "kaggle"].includes(b.id) && <button className="btn-ghost ml-auto" onClick={() => setS({ ...s, backends: s.backends.filter((_, j) => j !== i) })}><Trash2 size={13} /></button>}
                  </div>
                  <div className="mt-3 grid grid-cols-[1fr_220px_auto] gap-2">
                    <input className="input font-mono text-xs" placeholder={b.id === "kaggle" ? "https://xxxx.trycloudflare.com" : "http://127.0.0.1:8188"} value={b.url} onChange={(e) => setBackend(i, { url: e.target.value })} />
                    <input className="input font-mono text-xs" type="password" placeholder="Access token (if any)" value={b.token} onChange={(e) => setBackend(i, { token: e.target.value })} />
                    <button className="btn" onClick={() => test(b)} disabled={!b.url}><PlugZap size={14} /> Test</button>
                  </div>
                  {t === "testing" && <p className="mt-2 text-xs text-fog-500">Connecting…</p>}
                  {t && t !== "testing" && (t.online ? (
                    <p className="mt-2 flex items-center gap-1.5 text-xs text-accent"><Check size={13} /> Connected · {t.bridge?.gpu?.name ?? t.devices?.[0]?.name ?? "CPU"}{t.bridge ? "" : " · bridge node missing"}{t.engines ? ` · ${Object.values(t.engines).filter((e) => e.installed).length} model(s) installed` : ""}</p>
                  ) : <p className="mt-2 text-xs text-red-300">{t.error}</p>)}
                </div>
              );
            })}
            <button className="btn self-start" onClick={() => setS({ ...s, backends: [...s.backends, { id: `custom${Date.now().toString(36)}`, name: "Another GPU computer", url: "", token: "", kind: "remote" }] })}><Plus size={14} /> Add backend</button>
          </div>
        </section>

        <section>
          <h2 className="mb-1 text-sm font-semibold">Prompt enhancement</h2>
          <p className="mb-4 text-xs text-fog-500">Built-in enhancer works offline. For smarter rewrites, install the free <a className="underline" href="https://ollama.com" target="_blank" rel="noreferrer">Ollama</a> app, run <code className="rounded bg-ink-800 px-1">ollama pull llama3.2:3b</code>, then pick it here.</p>
          <div className="grid grid-cols-2 gap-3">
            <div><div className="label mb-2">Ollama address</div><input className="input font-mono text-xs" value={s.ollama_url} onChange={(e) => setS({ ...s, ollama_url: e.target.value })} /></div>
            <div><div className="label mb-2">Model</div>
              <select className="input" value={s.ollama_model} onChange={(e) => setS({ ...s, ollama_model: e.target.value })}>
                <option value="">Built-in enhancer (no LLM)</option>
                {ollama.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              {ollama.length === 0 && <p className="mt-1.5 text-[11px] text-fog-500">Ollama not detected.</p>}
            </div>
          </div>
        </section>

        <section>
          <h2 className="mb-1 text-sm font-semibold">Local tools</h2>
          <div className="grid grid-cols-2 gap-3">
            <div><div className="label mb-2">FFmpeg</div><input className="input font-mono text-xs" placeholder="Auto-detect" value={s.ffmpeg_path} onChange={(e) => setS({ ...s, ffmpeg_path: e.target.value })} />
              <p className="mt-1.5 text-[11px] text-fog-500">{health?.ffmpeg ? `Found: ${health.ffmpeg}` : "Not found. Run scripts/install.sh."}</p></div>
            <div><div className="label mb-2">Library location</div><div className="input font-mono text-xs text-fog-400">{health?.data_dir ?? "…"}</div></div>
          </div>
        </section>
      </div>
    </div>
  );
}
