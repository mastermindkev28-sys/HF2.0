// All calls go to the local FastAPI backend. In `npm run dev` set NEXT_PUBLIC_API=http://127.0.0.1:7860.
export const API = process.env.NEXT_PUBLIC_API ?? "";

export async function api<T = any>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const res = await fetch(`${API}${path}`, {
    ...rest,
    headers: json !== undefined ? { "Content-Type": "application/json", ...(rest.headers || {}) } : rest.headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const d = await res.json();
      msg = typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail ?? d);
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const fileUrl = (kind: "outputs" | "thumbs" | "assets" | "characters", name: string) =>
  `${API}/files/${kind}/${name}`;

export type Mode = "t2v" | "i2v" | "v2v";

export interface Resolution { id: string; label: string; pixels: number; note: string }
export interface ModelFile { filename: string; folder: string; url: string; size_gb: number }
export interface EngineInfo {
  id: string; name: string; family: string; description: string; license: string; homepage: string;
  modes: Mode[]; min_vram_gb: number; recommended_vram_gb: number; runs_on_cpu: boolean; cpu_note: string;
  files: ModelFile[]; total_size_gb: number; resolutions: Resolution[]; fps_options: number[];
  max_frames: number; frame_multiple: number; defaults: Record<string, any>; catalog_only: boolean;
}
export interface CameraMove { id: string; label: string; text: string }

export interface Generation {
  id: string; created_at: number; updated_at: number; status: "queued" | "running" | "done" | "error" | "cancelled";
  mode: string; engine: string; backend_id: string; prompt: string; final_prompt: string; negative_prompt: string;
  params: Record<string, any>; progress: number; progress_text: string; error: string | null;
  output_file: string | null; thumb_file: string | null; duration_s: number | null; elapsed_s: number | null;
  parent_id: string | null; character_id: string | null; saved: number;
}
export interface Character { id: string; created_at: number; name: string; description: string; images: string[] }
export interface Asset { id: string; created_at: number; kind: "image" | "video"; filename: string; original_name: string; width: number | null; height: number | null; duration_s: number | null }
export interface Backend { id: string; name: string; url: string; token: string; kind: string }
export interface Settings { backends: Backend[]; active_backend: string; ollama_url: string; ollama_model: string; ffmpeg_path: string }
export interface BackendStatus {
  id: string; name: string; url: string; online: boolean; error?: string;
  system?: Record<string, any>; devices?: { name: string; type: string; vram_total: number; vram_free: number }[];
  queue?: { running: number; pending: number };
  engines?: Record<string, { installed: boolean; missing: string[] }>;
  upscaler_installed?: boolean; nodes_ok?: boolean; bridge?: Record<string, any> | null;
}

export async function uploadAsset(file: File): Promise<Asset> {
  const fd = new FormData();
  fd.append("file", file);
  return api<Asset>("/api/assets", { method: "POST", body: fd });
}

export const MODE_LABEL: Record<string, string> = {
  t2v: "Text to Video", i2v: "Image to Video", v2v: "Video to Video", extend: "Extension",
  interpolate: "Interpolation", upscale_basic: "Upscale", upscale_ai: "AI Upscale", stitch: "Stitch",
};

export function timeAgo(ts: number) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

export function fmtDuration(s: number | null | undefined) {
  if (!s && s !== 0) return "";
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${Math.round(s % 60)}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}
