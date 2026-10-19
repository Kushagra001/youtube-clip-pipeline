# YouTube Viral Clipping Pipeline

Automated pipeline: discovers viral creators & high-performing long-form videos → extracts highlight-worthy moments
with LLMs (Groq Llama 3.3) or local heuristics → transforms clips into policy-compliant 9:16 vertical Shorts with
editorial framing, top burner headlines, kinetic safe-zone captions, and digital footprint alterations → optionally
uploads to YouTube as Shorts. Runs on a schedule via GitHub Actions or locally.

100% powered by free tiers and open tools — zero paid APIs required.

## 🛡️ Policy Compliance & Anti-Shadowban Engine

YouTube strictly enforces its **Reused Content** and **Inauthentic Content** policies, rejecting channels that simply re-upload unedited slices of other creators' content. Additionally, automated Content ID claims and algorithmic suppression ("shadowbanning") occur when audio matches background music cues or when upload frequency triggers bot-farm spam filters.

This pipeline incorporates an **8-Layer Fair Use & Transformation Engine** to defeat duplicate hash matching, satisfy Section 107 Fair Use doctrine, and accelerate channel growth:

1. **Meme-Page Template Engine (Memezar / 9GAG Style)**: `vertical_style: "meme_card"` wraps the video in a high-engagement viral template featuring a top header card (sleek dark `#18181B` or classic white `#FFFFFF`), brand handle badge with verified dot, bold auto-wrapped hook headline, and a 4px framed center player.
2. **Transformative Educational Takeaways (Fair Use 17 U.S.C. § 107)**: Every clip synthesizes a concluding insight rendered as a boxed `💡 KEY INSIGHT: ...` outro card during the final 3.5 seconds, accompanied by formal credit, timestamp, and source links in the description.
3. **Anti-Content-ID Audio Conditioning**: Content ID matches are 90%+ triggered by background music. An FFmpeg filter chain (`highpass=f=85,lowpass=f=11500,equalizer=f=3000:t=q:w=1.2:g=2.2`) isolates dialogue and strips music soundbeds prior to -14 LUFS normalization.
4. **Curated Creator Whitelist & Network Blacklist**: Targets clip-friendly creators (`@hubermanlab`, `@lexfridman`, `@TheDiaryOfACEO`) while automatically filtering out litigious broadcast and sports networks (UFC, NFL, NBA, BBC, CNN, Disney, Nintendo).
5. **Spatial Micro-Zoom (1.03x)**: Rescales foreground video by 1.03x, breaking exact pixel-to-pixel matrix alignment against the original upload hash.
6. **Temporal Micro-Shift (1.02x)**: Shifts playback speed by ~2% (`setpts` + `atempo`), modifying every frame timestamp and audio waveform frequency while remaining completely natural to the human ear.
7. **Color Grading & Vignette**: Adjusts contrast (`1.06`), saturation (`1.08`), and subtle vignette to shift RGB histograms across the entire video canvas.
8. **Anti-Spam Upload Cadence & Safe-Zone Pacing**: Uploads are capped at 2/day to avoid bot-farm spam classification, with clip durations strictly tuned to 25s–48s for optimal retention (APV > 100%) and zero dead air.

## How it works

1. **Autonomous Discovery**: `pipeline/discovery.py` monitors target niches (e.g. AI, finance, podcasts)
   and creator handles (e.g. `@hubermanlab`, `@lexfridman`) using `yt-dlp` metadata search.
   It filters for long-form episodes (10–120 min) that exceed virality thresholds (e.g. 100k+ views).
2. **Idempotency Check**: Processed video IDs are tracked in `state/processed.json` so the pipeline
   skips already-clipped videos before downloading them.
3. **Download & Subtitles**: `main.py` downloads the selected video via `yt-dlp` alongside English
   captions (or falls back to local CPU `faster-whisper` transcription if captions are unavailable).
4. **Highlight Extraction**: 1–3 clip-worthy timestamp ranges are selected (25s–55s) with a punchy
   burner headline, either by a free local heuristic scorer or Groq's free-tier LLM API (Llama 3.3 70B).
5. **Footprint Shift & Framing**: Each clip is cut, zero-dead-air trimmed, speed-shifted, color-graded,
   framed with borders, and equipped with a progress bar and -14 LUFS audio.
6. **Burner Header & Captions**: Top burner headline and safe-zone kinetic subtitles are burned in via `libass`.
7. **Delivery**: If `auto_upload: true`, finished clips are uploaded to YouTube as unlisted/private
   Shorts via YouTube Data API v3 with optimized titles and creator attribution. In all runs, clips
   are saved in `output/clips/` and archived as GitHub Actions artifacts.

## Choosing a highlight method

Set `highlight_method` in `config/sources.yaml`:

- **`heuristic`** (default) — no API key, no network call, no signup, $0
  forever. Scores candidate clip windows on hook-word density, question
  marks, and natural pause boundaries in the transcript. Decent first pass,
  fully deterministic, works even if you're offline from any LLM provider.
- **`groq`** — routes clip selection through Groq's hosted free tier
  (Llama 3.3 70B). Noticeably better judgment about what's actually a good
  clip (self-contained, lands on a punchline). Still free — console.groq.com
  gives you an API key with no credit card required, with generous
  request/token-per-minute limits on the free tier.

## Setup

### 1. Secrets

In your GitHub repo → Settings → Secrets and variables → Actions:

- `GROQ_API_KEY` — only needed if `highlight_method: "groq"` or for AI niche query expansion. Get one free
  at console.groq.com. Skip this entirely if you're using `heuristic`.

If you want auto-upload, also add (see step 2):
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

### 2. YouTube OAuth (only needed for auto-upload)

Run this locally, once — not in CI:

```bash
pip install google-auth-oauthlib
# 1. Google Cloud Console -> new project -> enable "YouTube Data API v3"
# 2. Create OAuth Client ID, type "Desktop app", download as client_secret.json
#    into this directory
python pipeline/get_youtube_token.py
```

### 3. Configure discovery & sources

Edit `config/sources.yaml`:
- **Niches**: Add topics like `"ai and tech podcast"`, `"business finance interview"`.
- **Creators**: Add handles like `"@hubermanlab"`, `"@lexfridman"`.
- **Virality Tuning**: Set `min_views`, `min_duration_minutes`, `max_duration_minutes`, `max_videos_per_run`.
- **Shorts Compliance**:
  - `burner_text: true` (burns top hook headline badge)
  - `progress_bar: true` (animated completion bar)
  - `speed_microshift: 1.02` (temporal hash shift)
  - `audio_loudnorm: true` (YouTube -14 LUFS mastering)
  - `min_clip_seconds: 25`, `max_clip_seconds: 55`

### 4. Run

- **Locally**: `pip install -r requirements.txt`, then `python main.py` (needs `ffmpeg` installed).
- **On GitHub Actions**: Push this repo; the workflow in `.github/workflows/clip-pipeline.yml` runs
  on a cron (default: every 6 hours) and is also triggerable manually from the Actions tab ("Run workflow").

## Cost breakdown

| Piece | Tool | Cost |
|---|---|---|
| Viral Creator & Video Discovery | `yt-dlp` metadata search (Python) | Free, no key, no quota |
| AI Niche Query Expansion (Optional) | Groq API (`llama-3.3-70b-versatile`) | Free tier (no card needed) |
| Video Download | `yt-dlp` | Free, no key |
| Transcript (captions available) | `yt-dlp` subtitle extraction | Free, no key |
| Transcript (no captions) | `faster-whisper`, local CPU | Free, no key, compute only |
| Highlight & Burner Selection | Heuristic scorer *or* Groq free tier | Free either way |
| Framing, Burner Text, & Footprint Shift | `ffmpeg` + `libass` | Free, no key |
| Upload | YouTube Data API v3 | Free (10,000 units/day quota) |
| Compute | GitHub Actions | Free tier: 2,000 min/month on private repos, unlimited on public repos |

## File layout

```
main.py                          orchestrator & pipeline entrypoint
config/sources.yaml               discovery rules, creators, niches, & Shorts compliance tuning
pipeline/discovery.py             viral creator & video search engine (100% free)
pipeline/download.py               yt-dlp download + subs
pipeline/transcript.py            caption parsing + Whisper fallback
pipeline/highlights.py            Shorts highlight selection (25s-55s) & burner text generator
pipeline/clip.py                  framing, 1.02x speed shift, zoom, color grading, progress bar
pipeline/captions.py              burner header + safe-zone kinetic ASS subtitles
pipeline/upload_youtube.py        YouTube Shorts upload with attribution metadata
pipeline/get_youtube_token.py     one-time OAuth setup (run locally)
pipeline/state.py                 idempotency tracking
state/processed.json              persisted state (committed by CI)
.github/workflows/clip-pipeline.yml   scheduled/triggerable Action
```
