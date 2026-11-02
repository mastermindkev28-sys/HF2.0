"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Wand2, ChevronDown, Dice5, Camera, Info, Type, ImageIcon, Clapperboard, AlertTriangle, Film, Plus, X } from "lucide-react";
import { api, Character, EngineInfo, fileUrl, Generation, Mode } from "@/lib/api";
import { useBackendStatus, useEngines, useSettings } from "@/lib/hooks";
import MediaPicker, { PickedMedia } from "@/components/MediaPicker";
import Preview from "@/components/Preview";
import { useToast } from "@/components/Toast";

type UIMode = Mode | "long";
interface Shot { prompt: string; duration_s: number; camera: string }
const MODES: { id: UIMode; label: string; icon: any }[] = [
  { id: "t2v", label: "Text to Video", icon: Type },
  { id: "i2v", label: "Image to Video", icon: ImageIcon },
  { id: "v2v", label: "Video to Video", icon: Clapperboard },
  { id: "long", label: "Long video", icon: Film },
];
const ASPECTS = ["16:9", "9:16", "1:1", "4:3"];

export default function CreatePage() {
  const toast = useToast();
  const meta = useEngines();
  const { settings } = useSettings();
  const [backendId, setBackendId] = useState<string>("");
  useEffect(() => { if (settings && !backendId) setBackendId(settings.active_backend); }, [settings, backendId]);
  const { status } = useBackendStatus(backendId, 30000);

  const [mode, setMode] = useState<UIMode>("t2v");
  const [shots, setShots] = useState<Shot[]>([
    { prompt: "", duration_s: 5, camera: "" }, { prompt: "", duration_s: 5, camera: "" }, { prompt: "", duration_s: 5, camera: "" },
  ]);
  const [engineId, setEngineId] = useState("wan22_ti2v_5b");
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState<string | null>(null);
  const [showNeg, setShowNeg] = useState(false);
  const [image, setImage] = useState<PickedMedia | null>(null);
  const [video, setVideo] = useState<PickedMedia | null>(null);
  const [aspect, setAspect] = useState("16:9");
  const [resolution, setResolution] = useState("");
  const [duration, setDuration] = useState(3);
  const [fps, setFps] = useState(24);
  const [steps, setSteps] = useState(20);
  const [cfg, setCfg] = useState(5);
  const [seed, setSeed] = useState(-1);
  const [camera, setCamera] = useState<string[]>([]);
  const [camIntensity, setCamIntensity] = useState(3);
  const [motionPrompt, setMotionPrompt] = useState("");
  const [motionIntensity, setMotionIntensity] = useState(3);
  const [denoise, setDenoise] = useState(0.6);
  const [finish1080, setFinish1080] = useState(false);
  const [characterId, setCharacterId] = useState("");
  const [characters, setCharacters] = useState<Character[]>([]);
  const [showAdv, setShowAdv] = useState(false);
  const [enhancing, setEnhancing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [current, setCurrent] = useState<Generation | null>(null);
  const [recent, setRecent] = useState<Generation[]>([]);

  const engines = useMemo(() => (meta?.engines ?? []).filter((e) => !e.catalog_only), [meta]);
  const engine: EngineInfo | undefined = engines.find((e) => e.id === engineId);
  const usable = engines.filter((e) => e.modes.includes(mode === "long" ? "i2v" : mode));

  // apply engine defaults when the engine changes
  const applyDefaults = useCallback((e: EngineInfo) => {
    setResolution(e.defaults.resolution);
    setFps(e.defaults.fps);
    setSteps(e.defaults.steps);
    setCfg(e.defaults.cfg);
    setDenoise(e.defaults.denoise ?? 0.6);
    setNegative(null);
  }, []);
  useEffect(() => { if (engine) applyDefaults(engine); }, [engine?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (engine && !engine.modes.includes(mode === "long" ? "i2v" : mode) && usable[0]) setEngineId(usable[0].id); }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadRecent = useCallback(() => api<{ generations: Generation[] }>("/api/generations?limit=12").then((r) => setRecent(r.generations)).catch(() => {}), []);
  useEffect(() => { loadRecent(); api<{ characters: Character[] }>("/api/characters").then((r) => setCharacters(r.characters)).catch(() => {}); }, [loadRecent]);

  // reuse a previous generation's settings: /?reuse=<id>
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("reuse");
    if (!id || !meta) return;
    api<Generation>(`/api/generations/${id}`).then((g) => {
      const p = g.params;
      if (["t2v", "i2v", "v2v"].includes(g.mode)) setMode(g.mode as Mode);
      setEngineId(g.engine);
      setTimeout(() => {
        setPrompt(g.prompt); setNegative(g.negative_prompt); setAspect(p.aspect); setResolution(p.resolution);
        setDuration(p.duration_s); setFps(p.fps); setSteps(p.steps); setCfg(p.cfg); setSeed(p.seed);
        setCamera(p.camera ?? []); setCamIntensity(p.camera_intensity ?? 3); setMotionPrompt(p.motion_prompt ?? "");
        if (p.motion_intensity) setMotionIntensity(p.motion_intensity);
        if (p.denoise) setDenoise(p.denoise);
        setFinish1080(!!p.finish_1080p);
        setCharacterId(g.character_id ?? "");
        setCurrent(g);
      }, 50);
    }).catch(() => {});
  }, [meta]);

  // poll the active generation
  useEffect(() => {
    if (!current || !["queued", "running"].includes(current.status)) return;
    const t = setInterval(async () => {
      try {
        const g = await api<Generation>(`/api/generations/${current.id}`);
        setCurrent(g);
        if (!["queued", "running"].includes(g.status)) {
          loadRecent();
          if (g.status === "done") toast("Your video is ready");
        }
      } catch {}
    }, 1500);
    return () => clearInterval(t);
  }, [current?.id, current?.status, loadRecent, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  const maxDuration = engine ? Math.floor(engine.max_frames / fps) : 5;
  useEffect(() => { if (duration > maxDuration) setDuration(maxDuration); }, [maxDuration, duration]);

  const engineStatus = status?.engines?.[engineId];
  const character = characters.find((c) => c.id === characterId);

  const toggleCam = (id: string) => setCamera((c) => {
    if (id === "static") return c.includes("static") ? [] : ["static"];
    const without = c.filter((x) => x !== "static");
    if (without.includes(id)) return without.filter((x) => x !== id);
    return [...without, id].slice(-2);
  });

  const enhance = async () => {
    setEnhancing(true);
    try {
      const r = await api<{ prompt: string; method: string; note?: string }>("/api/enhance", { method: "POST", json: { prompt } });
      setPrompt(r.prompt);
      toast(r.note ?? (r.method === "built-in" ? "Enhanced with the built-in enhancer" : `Enhanced with ${r.method.replace("ollama:", "Ollama · ")}`));
    } catch (e: any) { toast(e.message, "err"); } finally { setEnhancing(false); }
  };

  const generate = async () => {
    setSubmitting(true);
    try {
      if (mode === "long") {
        const g = await api<Generation>("/api/generate/long", {
          method: "POST",
          json: {
            engine: engineId, backend_id: backendId, negative: negative ?? undefined, aspect, resolution, fps, steps, cfg, seed,
            camera_intensity: camIntensity, image: image?.ref, character_id: characterId || undefined, finish_1080p: finish1080,
            shots: shots.filter((x) => x.prompt.trim()).map((x) => ({ prompt: x.prompt, duration_s: x.duration_s, camera: x.camera ? [x.camera] : [] })),
          },
        });
        setCurrent(g);
        loadRecent();
        return;
      }
      const g = await api<Generation>("/api/generate", {
        method: "POST",
        json: {
          mode, engine: engineId, backend_id: backendId, prompt, negative: negative ?? undefined, aspect, resolution,
          duration_s: duration, fps, steps, cfg, seed, camera, camera_intensity: camIntensity,
          motion_prompt: motionPrompt, motion_intensity: mode === "i2v" ? motionIntensity : undefined,
          image: mode === "i2v" ? image?.ref : undefined, video: mode === "v2v" ? video?.ref : undefined,
          denoise: mode === "v2v" ? denoise : undefined, character_id: characterId || undefined, finish_1080p: finish1080,
        },
      });
      setCurrent(g);
      loadRecent();
    } catch (e: any) { toast(e.message, "err"); } finally { setSubmitting(false); }
  };

  const totalLong = shots.filter((x) => x.prompt.trim()).reduce((a, x) => a + x.duration_s, 0);
  const canGenerate = !!engine && !submitting && (mode !== "long" || (totalLong > 0 && totalLong <= 60)) && (mode !== "t2v" || prompt.trim()) && (mode !== "i2v" || image || character?.images.length) && (mode !== "v2v" || video);

  return (
    <div className="grid min-h-screen grid-cols-1 xl:grid-cols-[440px_1fr]">
      {/* ---------------- controls ---------------- */}
      <section className="flex flex-col gap-5 overflow-y-auto border-r border-white/[0.06] bg-ink-950 p-5 xl:h-screen">
        <div className="grid grid-cols-2 gap-1 rounded-xl border border-white/[0.06] bg-ink-900 p-1">
          {MODES.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setMode(id)}
              className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs transition ${mode === id ? "bg-ink-700 text-fog-100" : "text-fog-500 hover:text-fog-200"}`}>
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>

        {mode === "i2v" && (
          <Field label="Image" hint={character?.images.length && !image ? `Using ${character.name}'s reference image` : "The subject's look is kept from this image"}>
            <MediaPicker kind="image" value={image} onChange={setImage} />
          </Field>
        )}
        {mode === "long" && (
          <>
            <Field label="Starting image (optional)" hint="Leave empty to start from text. With an image (or a character), shot 1 starts from it.">
              <MediaPicker kind="image" value={image} onChange={setImage} />
            </Field>
            <Field label={`Shots · ${totalLong.toFixed(0)}s total`} hint={`Each shot is up to ${Math.floor((engine?.max_frames ?? 121) / fps)}s (the model's limit). Every shot continues from the last frame of the one before, then they're joined into one video. Long chains can slowly drift in detail.`}>
              <div className="flex flex-col gap-2">
                {shots.map((sh, i) => (
                  <div key={i} className="rounded-xl border border-white/[0.07] bg-ink-900 p-3">
                    <div className="mb-2 flex items-center justify-between text-[11px] text-fog-500">
                      <span>Shot {i + 1}</span>
                      {shots.length > 1 && <button className="btn-ghost -mr-2 py-0.5" onClick={() => setShots(shots.filter((_, j) => j !== i))}><X size={12} /></button>}
                    </div>
                    <textarea className="input min-h-[64px] text-sm" value={sh.prompt} placeholder={i === 0 ? "A woman in a cream sweater picks up a glass serum bottle in a sunlit bathroom" : "What happens next…"}
                      onChange={(e) => setShots(shots.map((x, j) => (j === i ? { ...x, prompt: e.target.value } : x)))} />
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <select className="input py-1.5 text-xs" value={sh.camera} onChange={(e) => setShots(shots.map((x, j) => (j === i ? { ...x, camera: e.target.value } : x)))}>
                        <option value="">No camera move</option>
                        {(meta?.camera_moves ?? []).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                      </select>
                      <select className="input py-1.5 text-xs" value={sh.duration_s} onChange={(e) => setShots(shots.map((x, j) => (j === i ? { ...x, duration_s: Number(e.target.value) } : x)))}>
                        {Array.from({ length: Math.max(1, Math.floor((engine?.max_frames ?? 121) / fps)) }, (_, k) => k + 1).map((d) => <option key={d} value={d}>{d}s</option>)}
                      </select>
                    </div>
                  </div>
                ))}
                <button className="btn self-start text-xs" disabled={totalLong >= 60} onClick={() => setShots([...shots, { prompt: "", duration_s: Math.min(5, Math.floor((engine?.max_frames ?? 121) / fps)), camera: "" }])}><Plus size={13} /> Add shot</button>
                {totalLong > 60 && <p className="text-xs text-red-300">The limit is 60 seconds.</p>}
              </div>
            </Field>
          </>
        )}
        {mode === "v2v" && (
          <Field label="Source video" hint="Restyled with partial denoising: lower strength keeps more of the original">
            <MediaPicker kind="video" value={video} onChange={setVideo} />
          </Field>
        )}

        {mode !== "long" && <Field label={mode === "t2v" ? "Prompt" : mode === "i2v" ? "What happens (optional)" : "New style"}
          right={<button className="btn-ghost -mr-2" disabled={!prompt.trim() || enhancing} onClick={enhance}><Wand2 size={13} /> {enhancing ? "Enhancing…" : "Enhance"}</button>}>
          <textarea className="input min-h-[120px] resize-y leading-relaxed" value={prompt} onChange={(e) => setPrompt(e.target.value)}
            placeholder={mode === "t2v" ? "A lone astronaut walks across red dunes at golden hour, dust drifting in the wind…" : mode === "i2v" ? "She turns toward the camera and smiles, hair moving in the breeze" : "Hand-painted anime style, warm sunset palette"} />
          <button className="mt-2 text-xs text-fog-500 hover:text-fog-300" onClick={() => setShowNeg(!showNeg)}>{showNeg ? "− Hide" : "+ Add"} negative prompt</button>
          {showNeg && <textarea className="input mt-2 min-h-[70px] text-xs" value={negative ?? engine?.defaults.negative ?? ""} onChange={(e) => setNegative(e.target.value)} placeholder="What to avoid" />}
        </Field>}

        {mode === "i2v" && (
          <Field label="Motion">
            <input className="input" value={motionPrompt} onChange={(e) => setMotionPrompt(e.target.value)} placeholder="e.g. waves crash, leaves sway, steam rises" />
            <Slider label="Movement intensity" min={1} max={5} step={1} value={motionIntensity} onChange={setMotionIntensity} display={["Minimal", "Gentle", "Natural", "Lively", "Intense"][motionIntensity - 1]} />
          </Field>
        )}
        {mode === "v2v" && (
          <Field label="Transformation strength">
            <Slider label="" min={0.2} max={0.95} step={0.05} value={denoise} onChange={setDenoise} display={denoise < 0.45 ? `${denoise.toFixed(2)} · subtle` : denoise < 0.7 ? `${denoise.toFixed(2)} · balanced` : `${denoise.toFixed(2)} · strong`} />
          </Field>
        )}

        <Field label="Character" hint="The description is added to the prompt; in Image to Video the reference image drives the look">
          <select className="input" value={characterId} onChange={(e) => setCharacterId(e.target.value)}>
            <option value="">None</option>
            {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {character && (
            <div className="mt-2 flex items-center gap-2">
              {character.images.slice(0, 4).map((i) => /* eslint-disable-next-line @next/next/no-img-element */ <img key={i} src={fileUrl("characters", `${character.id}/${i}`)} alt="" className="h-10 w-10 rounded-lg object-cover" />)}
              <span className="line-clamp-2 text-xs text-fog-500">{character.description}</span>
            </div>
          )}
        </Field>

        <Field label="Model">
          <div className="flex flex-col gap-2">
            {usable.map((e) => {
              const st = status?.engines?.[e.id];
              return (
                <button key={e.id} onClick={() => setEngineId(e.id)}
                  className={`rounded-xl border p-3 text-left transition ${engineId === e.id ? "border-accent/50 bg-accent/[0.04]" : "border-white/[0.07] bg-ink-900 hover:border-white/15"}`}>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{e.name}</span>
                    {status?.online ? (st?.installed ? <span className="badge border-accent/30 text-accent">Ready</span> : <span className="badge">Not installed</span>) : <span className="badge">Offline</span>}
                  </div>
                  <div className="mt-1 text-xs text-fog-500">{e.family} · {e.license.split(" (")[0]}</div>
                </button>
              );
            })}
          </div>
          {status?.online && engineStatus && !engineStatus.installed && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-amber-300/90"><AlertTriangle size={13} className="mt-0.5 shrink-0" /> Not installed on {status.name}. <Link className="underline" href="/models/">Install it in Explore Models</Link>.</p>
          )}
          {status && !status.online && <p className="mt-2 text-xs text-red-300/90">{status.name} is offline: {status.error}. <Link className="underline" href="/settings/">Settings</Link></p>}
        </Field>

        <Field label="Aspect ratio">
          <div className="flex flex-wrap gap-1.5">{ASPECTS.map((a) => <button key={a} className={`chip ${aspect === a ? "chip-on" : ""}`} onClick={() => setAspect(a)}><AspectIcon a={a} />{a}</button>)}</div>
        </Field>

        <Field label="Resolution" hint={engine?.resolutions.find((r) => r.id === resolution)?.note}>
          <div className="flex flex-wrap gap-1.5">{engine?.resolutions.map((r) => <button key={r.id} className={`chip ${resolution === r.id ? "chip-on" : ""}`} onClick={() => setResolution(r.id)}>{r.label}</button>)}</div>
          <label className="mt-3 flex cursor-pointer items-start gap-2.5 rounded-xl border border-white/[0.07] bg-ink-900 p-3">
            <input type="checkbox" className="mt-0.5" checked={finish1080} onChange={(e) => setFinish1080(e.target.checked)} />
            <span>
              <span className="text-sm text-fog-100">Finish in 1080p</span>
              <span className="block text-[11px] leading-snug text-fog-500">
                Generates at the model&apos;s resolution, then AI-upscales (Real-ESRGAN) to {aspect === "9:16" ? "1080×1920" : aspect === "1:1" ? "1080×1080" : aspect === "4:3" ? "1440×1080" : "1920×1080"}. Best from 720p. Needs a GPU backend with the upscaler installed.
              </span>
            </span>
          </label>
        </Field>

        <div className="grid grid-cols-2 gap-4">
          {mode !== "long" ? <Field label="Duration">
            <Slider label="" min={1} max={Math.max(1, maxDuration)} step={1} value={duration} onChange={setDuration} display={`${duration}s`} />
          </Field> : <div />}
          <Field label="FPS">
            <div className="flex flex-wrap gap-1.5">{engine?.fps_options.map((f) => <button key={f} className={`chip ${fps === f ? "chip-on" : ""}`} onClick={() => setFps(f)}>{f}</button>)}</div>
          </Field>
        </div>

        {mode !== "long" && <CameraPanel moves={meta?.camera_moves ?? []} selected={camera} toggle={toggleCam} intensity={camIntensity} setIntensity={setCamIntensity} />}

        <div>
          <button className="flex w-full items-center justify-between text-left" onClick={() => setShowAdv(!showAdv)}>
            <span className="label">Advanced</span>
            <ChevronDown size={14} className={`text-fog-500 transition ${showAdv ? "rotate-180" : ""}`} />
          </button>
          {showAdv && (
            <div className="mt-3 flex flex-col gap-4">
              <Slider label="Inference steps (quality vs speed)" min={4} max={50} step={1} value={steps} onChange={setSteps} display={String(steps)} />
              <Slider label="Guidance (CFG)" min={1} max={10} step={0.5} value={cfg} onChange={setCfg} display={cfg.toFixed(1)} />
              <div>
                <div className="mb-1.5 text-xs text-fog-400">Seed</div>
                <div className="flex gap-2">
                  <input className="input" type="number" value={seed < 0 ? "" : seed} placeholder="Random" onChange={(e) => setSeed(e.target.value === "" ? -1 : parseInt(e.target.value))} />
                  <button className="btn" title="Random" onClick={() => setSeed(-1)}><Dice5 size={14} /></button>
                </div>
              </div>
              <div>
                <div className="mb-1.5 text-xs text-fog-400">Run on</div>
                <select className="input" value={backendId} onChange={(e) => setBackendId(e.target.value)}>
                  {settings?.backends.map((b) => <option key={b.id} value={b.id}>{b.name}{b.url ? "" : " (no address)"}</option>)}
                </select>
              </div>
              {engine && <p className="text-xs text-fog-500">Output: {calcDims(engine, aspect, resolution)} · {calcFrames(engine, duration, fps)} frames</p>}
            </div>
          )}
        </div>

        <div className="sticky -bottom-5 -mx-5 mt-auto border-t border-white/[0.06] bg-ink-950/95 p-5 backdrop-blur">
          <button className="btn-primary w-full py-3 text-[15px]" disabled={!canGenerate} onClick={generate}>
            {submitting ? "Queuing…" : "Generate"}
          </button>
          {engine && status?.online === false && <p className="mt-2 text-center text-[11px] text-fog-500">The job will wait in the queue and fail with a clear error if the backend stays offline.</p>}
        </div>
      </section>

      {/* ---------------- preview ---------------- */}
      <section className="flex flex-col gap-6 p-6 xl:h-screen xl:overflow-y-auto">
        <Preview gen={current} aspect={aspect} onNew={(g) => { setCurrent(g); loadRecent(); }} onUpdate={setCurrent} />
        <div>
          <div className="mb-3 flex items-center justify-between">
            <span className="label">Recent</span>
            <Link href="/generations/" className="text-xs text-fog-500 hover:text-fog-200">View all →</Link>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 2xl:grid-cols-6">
            {recent.map((g) => (
              <button key={g.id} onClick={() => setCurrent(g)} className={`group overflow-hidden rounded-xl border text-left transition ${current?.id === g.id ? "border-accent/60" : "border-white/[0.06] hover:border-white/20"}`}>
                <div className="relative aspect-video bg-ink-850">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {g.thumb_file && <img src={fileUrl("thumbs", g.thumb_file)} alt="" className="h-full w-full object-cover" />}
                  {g.status !== "done" && <div className="absolute inset-0 grid place-items-center text-[10px] uppercase tracking-wider text-fog-400">{g.status === "running" ? `${Math.round(g.progress * 100)}%` : g.status}</div>}
                </div>
                <div className="truncate px-2 py-1.5 text-[11px] text-fog-400">{g.prompt || g.mode}</div>
              </button>
            ))}
            {recent.length === 0 && <p className="col-span-full text-sm text-fog-500">Nothing generated yet.</p>}
          </div>
        </div>
      </section>
    </div>
  );
}

function calcDims(e: EngineInfo, aspect: string, resId: string) {
  const r = e.resolutions.find((x) => x.id === resId) ?? e.resolutions[0];
  const [a, b] = aspect.split(":").map(Number);
  const ar = a / b;
  const w = Math.sqrt(r.pixels * ar), h = w / ar, m = 32;
  return `${Math.max(m, Math.round(w / m) * m)}×${Math.max(m, Math.round(h / m) * m)}`;
}
function calcFrames(e: EngineInfo, d: number, fps: number) {
  const m = e.frame_multiple, n = Math.max(1, Math.round((Math.round(d * fps) - 1) / m));
  return Math.min(m * n + 1, e.max_frames);
}

function Field({ label, hint, right, children }: { label: string; hint?: string | false; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between"><span className="label">{label}</span>{right}</div>
      {children}
      {hint && <p className="mt-1.5 text-[11px] leading-snug text-fog-500">{hint}</p>}
    </div>
  );
}

function Slider({ label, min, max, step, value, onChange, display }: { label: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void; display: string }) {
  return (
    <div className="mt-1">
      <div className="mb-1 flex justify-between text-xs"><span className="text-fog-400">{label}</span><span className="font-mono text-fog-300">{display}</span></div>
      <input type="range" className="w-full" min={min} max={max} step={step} value={value} onChange={(e) => onChange(parseFloat(e.target.value))} />
    </div>
  );
}

function AspectIcon({ a }: { a: string }) {
  const [w, h] = a.split(":").map(Number);
  const s = 12 / Math.max(w, h);
  return <span className="inline-block rounded-[2px] border border-current" style={{ width: w * s, height: h * s }} />;
}

function CameraPanel({ moves, selected, toggle, intensity, setIntensity }: { moves: { id: string; label: string; text: string }[]; selected: string[]; toggle: (id: string) => void; intensity: number; setIntensity: (n: number) => void }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="label flex items-center gap-1.5"><Camera size={12} /> Camera</span>
        <span className="group relative">
          <Info size={13} className="text-fog-500" />
          <span className="pointer-events-none absolute right-0 top-5 z-10 hidden w-64 rounded-lg border border-white/10 bg-ink-800 p-3 text-[11px] leading-relaxed text-fog-300 shadow-xl group-hover:block">
            Prompt-guided: Wan 2.2 5B and LTX 2B have no native camera-path input, so each move is written into the prompt in wording these models respond to. Results usually follow it, but it isn't guaranteed. Pick up to two.
          </span>
        </span>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {moves.map((m) => (
          <button key={m.id} title={m.text} onClick={() => toggle(m.id)} className={`chip justify-center px-2 ${selected.includes(m.id) ? "chip-on" : ""}`}>{m.label}</button>
        ))}
      </div>
      {selected.length > 0 && !selected.includes("static") && (
        <Slider label="Camera intensity" min={1} max={5} step={1} value={intensity} onChange={setIntensity} display={["Very subtle", "Gentle", "Moderate", "Dynamic", "Intense"][intensity - 1]} />
      )}
    </div>
  );
}
