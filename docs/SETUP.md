# HIGGS Studio · setup and launch guide

HIGGS Studio is your private AI video studio. The app (interface, library, files, FFmpeg tools) runs on
your computer. Video generation runs on a **ComfyUI backend**, which can be:

| Backend | What it is | Cost | Good for |
|---|---|---|---|
| **Kaggle free GPU** | ComfyUI in a free Kaggle notebook on an NVIDIA T4 (16 GB) | Free, ~30 GPU h/week, 12 h max per session | Wan 2.2 5B and LTX at real quality |
| **This computer** | ComfyUI installed next to the app | Free, unlimited | Offline/private drafts. On an Intel Mac this is CPU-only: LTX 2B, low-res, slow |
| **Another GPU computer** | Any ComfyUI you can reach by URL | Free (your hardware) | If you later get an NVIDIA PC |

There are no paid APIs anywhere in the app, no credits, and no accounts besides Kaggle's.

---

## 1. Install (once)

Requirements: macOS 12+ or Linux, Python 3.10–3.13, git, ~5 GB free (plus models). Node.js is optional
(a pre-built interface is included).

```bash
cd ~/Desktop/"HIGGS 2.0"
git clone https://github.com/mastermindkev28-sys/HF2.0 app
bash app/scripts/install.sh
```

The installer:
- downloads a standalone FFmpeg into `runtime/bin` (no Homebrew),
- creates the studio's Python environment and builds the interface,
- installs ComfyUI into `runtime/ComfyUI` with the right PyTorch for your machine
  (Intel Mac: PyTorch 2.2.2 CPU, the last version published for Intel Macs),
- installs the HIGGS bridge node into ComfyUI (model manager + hardware stats).

Add `--with-ltx` to also download LTX-Video 2B (~11.5 GB) for local generation, or `--no-comfy` to skip
local ComfyUI entirely and use Kaggle only.

Folder layout afterwards:

```
HIGGS 2.0/
  app/        this repository (code)  ← "Start HIGGS Studio.command" lives here
  app/data/   your library: videos, thumbnails, uploads, characters, studio.db
  runtime/    ffmpeg, ComfyUI, its Python env, and model weights
```

## 2. Launch

- **Mac:** double-click `app/Start HIGGS Studio.command` (first time: right-click → Open, to get past
  Gatekeeper). Drag it to the Dock for one-click launching.
- **Terminal:** `bash app/scripts/start.sh`

It starts local ComfyUI (if installed) and the studio, then opens **http://127.0.0.1:7860**.
Keep the window open; Ctrl+C stops everything. Logs: `app/data/logs/`.

## 3. Connect the free Kaggle GPU (each session)

One-time: create a Kaggle account, verify your phone number (Kaggle requires it for GPUs and internet),
then **Create → New Notebook → File → Import Notebook** and upload `kaggle/higgs_studio_kaggle.ipynb`.

Every time you want to generate on the GPU:
1. Open the notebook. In the right sidebar set **Accelerator: GPU T4 x2** and **Internet: On**.
2. **Run All**. After ~5–10 minutes (installing ComfyUI and downloading ~30 GB of models) the
   "Start ComfyUI" cell prints an **Address** (`https://….trycloudflare.com`) and a **Token**.
3. In the studio: **Settings → Kaggle free GPU** → paste both → **Test** → select it as default → **Save**.
4. Generate. When finished, stop the Kaggle session to save your weekly GPU hours.

Honest caveats:
- The address and token change every session.
- Kaggle may stop idle sessions, and sessions end after 12 hours.
- Kaggle doesn't publish a clear rule about serving web apps from notebooks; some users report web-UI
  sessions being stopped. The notebook only exposes ComfyUI's API behind a random token, but if Kaggle
  stops the session, just start it again.
- Free Cloudflare "quick tunnels" have no uptime guarantee.

## 4. Models

Open **Explore Models** and choose the backend at the top right. **Install** downloads the weights from
Hugging Face directly onto that backend; **Remove** deletes them. Status shows Ready / Not installed.

| Engine | Modes | Needs | Notes |
|---|---|---|---|
| Wan 2.2 TI2V 5B | text→video, image→video, video→video | 12–16 GB GPU | Primary engine. 24 fps, up to 5 s, 480p–720p |
| LTX-Video 2B distilled | text→video, image→video, video→video | 6 GB GPU, or CPU | Fast drafts; the only one that runs on an Intel Mac CPU |
| Real-ESRGAN ×2 | upscale | any | AI upscaling of finished clips |
| Wan 2.2 A14B, HunyuanVideo | — | 24 GB+ GPU | Listed for reference; not runnable on your current backends |

## 5. What each feature really does

- **Camera controls** are prompt-guided: neither engine accepts a camera path, so each move is written
  into the prompt in wording these models respond to. Usually followed, never guaranteed. The UI says so.
- **Character consistency:** in Image to Video the character's first reference image is the starting
  frame (strong identity carry-over). In Text to Video the saved description is added to the prompt
  (similar, not identical). There's no identity adapter for these models, so none is claimed.
- **Video to Video** re-renders your clip through the model with partial denoising ("strength").
  Lower strength keeps more of the original composition.
- **Long video** (Create → Long video): 15–60 s videos built from shots of up to 5 s each (the model's
  limit). Shot 1 starts from your text, image or character; each next shot continues from the previous
  shot's last frame with image-to-video; all shots are joined, then optionally finished in 1080p. Each shot
  can have its own prompt and camera move, so it doubles as a simple storyboard. Expect gradual drift in
  fine detail over many shots. On the Kaggle T4 a 30 s video means six Wan generations back to back.
- **Extend** takes the last frame, generates an image-to-video continuation, and joins the two clips.
- **Finish in 1080p** (Create page) and **Enhance → AI upscale to 1080p**: the model generates at its
  native resolution (Wan 2.2: 720p), then Real-ESRGAN ×2 on the backend upscales it and FFmpeg fits it to
  an exact 1920×1080 / 1080×1920 / 1080×1080 / 1440×1080 frame. No free model that fits a 16 GB GPU generates
  native 1080p at a usable speed. Use a GPU backend; on a CPU this step is very slow.
- **Enhance → AI upscale** runs Real-ESRGAN on the backend. **Quick upscale** and **Smooth to 48 fps**
  run FFmpeg on your computer (classical, not AI).
- **Stitch:** select clips in My Generations and join them in order.
- **Prompt enhancement:** built-in rule-based enhancer offline; or install the free Ollama app, pull a
  small model (`ollama pull llama3.2:3b`) and pick it in Settings.
- Not implemented (no suitable free local model wired up yet): AI sound effects, music, voiceover,
  lip-sync, first/last-frame conditioning, storyboards. The engine adapter system is built so these can
  be added as new adapters later.

## 6. Speed expectations

Measured numbers are recorded in `docs/TESTING.md`. Rough guide:
- Kaggle T4, Wan 2.2 5B, 480p, 3 s, 20 steps: several minutes per clip; 720p 5 s is much slower.
- Kaggle T4, LTX 2B, 512p, 3 s, 8 steps: around a minute.
- Intel Mac CPU, LTX 2B, 320p, 2–3 s: tens of minutes.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Sidebar says backend offline | Local: is the start window still open? Kaggle: is the notebook running, and did you paste the *new* address? |
| "Model … is not installed on this backend" | Explore Models → Install, on the backend you're generating with |
| "rejected the access token" | Re-copy the token from the Kaggle cell output |
| Out-of-memory error | Lower resolution or duration |
| `ffmpeg not found` | Re-run `bash app/scripts/install.sh` |
| Anything else | `app/data/logs/studio.log` and `comfyui.log` |

## 8. Updating

```bash
cd ~/Desktop/"HIGGS 2.0"/app && git pull && bash scripts/install.sh
```
Your library in `app/data/` is never touched by updates.
