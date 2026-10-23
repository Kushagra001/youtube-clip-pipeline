# YouTube Clipping Pipeline - Project Progress & Roadmap

Tracking document for current codebase status, identified issues, bug fixes, performance optimizations, and future enhancements.

---

## 📊 Pipeline Status Overview

| Component | Status | Details |
|---|---|---|
| **Autonomous Discovery** | 🟢 Complete | `yt-dlp` metadata search + optional Groq niche expansion |
| **Download Engine** | 🟢 Optimized | Two-stage targeted download: subtitles first, then only 30-55s clip sections |
| **Transcript Generation** | 🟢 Functional | Parses WebVTT auto-captions; dual fallback to faster-whisper or openai-whisper |
| **Highlight Extraction** | 🟢 Complete | Deterministic heuristic + Groq Llama 3.3 with graceful fallback & token guard |
| **Editorial Framing & Transform** | 🟢 Complete | 9:16 layout, 1.02x speed shift, 1.03x zoom, color grade, progress bar |
| **Meme Template Engine (Memezar/9GAG)** | 🟢 Complete | Top meme header card (dark/light), brand badge/handle, framed player |
| **Captions & Subtitle Sync** | 🟢 Hardened | Microsecond-accurate word-timing VTT parser, kinetic 2-3 word highlight, HTML entity unescape, speaker tag removal, collision-free cutoff |
| **YouTube Shorts Upload** | 🟢 Hardened | OAuth upload, quota budget tracking, and fair use attribution |
| **CI/CD Workflow** | 🟢 Hardened | Scheduled 6-hour cron, fonts installed, cache purge, git rebase push |
| **Fair Use & Policy Engine** | 🟢 Complete | Curated whitelist/blacklist, audio conditioning, transformative takeaway cards |
| **Growth & Anti-Shadowban** | 🟢 Complete | High-retention window (25-48s), seamless looping, 2 uploads/day anti-spam cap |
| **Visual Polish & Outro Branding** | 🟢 Complete | High-res 512x512 circular vector logos for 10 channels, FFmpeg alpha fade overlay, signature kinetic progress bar colors, zero missing glyph tofu boxes |
| **Channel Niche & Brand Identity** | 🟢 Hardened | 10 Channel configurations, bespoke accent color palettes, duration tuning, state isolation, multi-token upload support |
| **Smart Speaker Auto-Framing & Split-Screen** | 🟢 Complete (Phase 8) | OpenCV face detection, dynamic speaker centering, stacked dual-panel layout |
| **Multi-Platform, Webhooks & Smart Scheduling** | 🟢 Complete (Phase 9) | Telegram & Discord rich alerts, TikTok & IG Reels packaging bundles, peak-hour publishAt scheduler |
| **Retention Analytics & Self-Tuning Loop** | 🟢 Complete (Phase 10) | Zero-quota performance tracker, creator retention indices, discovery self-tuning |

---

## 🛠️ Step-by-Step Action Plan

### Phase 1: Critical Bug Fixes, Template Engine & Stability (High Priority)

- [x] **Step 1.1: Fix Subtitle Timing Desync with Speed Micro-Shift**
  - **Issue**: [pipeline/clip.py](pipeline/clip.py) shifts video and audio speed by `speed_factor` (e.g. `1.02x`), compressing the total playback duration. [pipeline/captions.py](pipeline/captions.py) previously created subtitle cue timestamps using raw, unscaled transcript times.
  - **Solution**: Implemented `speed_factor` scaling on cue start and end timestamps in `captions.build_ass_file()` and passed from `main.py`.
  - **Target Files**: [main.py](main.py), [pipeline/captions.py](pipeline/captions.py).

- [x] **Step 1.2: Fix FFmpeg `ass=` Filter Windows Path Escaping**
  - **Issue**: In [pipeline/captions.py](pipeline/captions.py), `ffmpeg -vf ass={ass_filter_path}` fails on Windows when the path contains drive letters (e.g. `C:`) because FFmpeg interprets `:` as a filter option separator.
  - **Solution**: Normalized path with forward slashes and escaped colons (`ass=filename='C\:/...'`).
  - **Target Files**: [pipeline/captions.py](pipeline/captions.py).

- [x] **Step 1.3: Add Graceful Fallback & Token Truncation for Groq Highlight Selection**
  - **Issue**: If `highlight_method: "groq"` is selected, passing a 2-hour uncompressed transcript (~35k+ tokens) can exceed Groq free-tier Tokens-Per-Minute (TPM) limits. Any API error or missing key crashed the pipeline.
  - **Solution**: Added candidate window condensation for long transcripts and wrapped Groq calls with automatic fallback to `find_highlights_heuristic`.
  - **Target Files**: [pipeline/highlights.py](pipeline/highlights.py).

- [x] **Step 1.4: Implement Meme-Page Video Template Engine (Memezar / 9GAG Style)**
  - **Concept**: Emulate the viral aesthetic popularized by top meme pages (Memezar, 9GAG, Pubity, Daquan) to maximize watch time, instant hook recognition, and brand recall:
    1. **Top Meme Card / Tweet Box Header**:
       - High-contrast banner card (choice of Classic Light `#FFFFFF` or Sleek Dark `#18181B`).
       - Channel/brand handle badge (e.g., `@yourchannel` with blue verification dot badge).
       - Bold, reaction-driven headline text with multi-line auto-wrapping.
    2. **Framed Center Video Canvas**:
       - Centered video player with clean 4px border outline card styling.
       - Ambient blurred backdrop with contrast/vignette grade.
    3. **Safe-Zone Subtitles & Kinetic Progress Bar**:
       - Fast-paced 3–4 word subtitles in the lower-middle safe zone (clear of YouTube Shorts UI).
       - Kinetic progress bar accent along the canvas bottom.
    4. **Configurable Settings**:
       - Set `template_style: "meme_card"` in [config/sources.yaml](config/sources.yaml) with options for `theme: "dark" | "light"`, `channel_handle: "@handle"`, and `show_badge: true`.
  - **Target Files**: [config/sources.yaml](config/sources.yaml), [pipeline/clip.py](pipeline/clip.py), [pipeline/captions.py](pipeline/captions.py), [main.py](main.py).

---

### Phase 2: Performance & Bandwidth Optimization

- [x] **Step 2.1: Implement Two-Stage Targeted Video Downloads**
  - **Issue**: [pipeline/download.py](pipeline/download.py) previously downloaded the entire 10–120 minute 1080p source video (~1GB–5GB) upfront before finding highlights.
  - **Solution**: Implemented `download_subtitles()` to fetch transcript first (<50KB in ~2s), and `download_clip_section()` to pull only the specific 30-55s clip range via `yt-dlp --download-sections`, saving ~98% bandwidth and runner disk space.
  - **Target Files**: [pipeline/download.py](pipeline/download.py), [main.py](main.py), [config/sources.yaml](config/sources.yaml).

- [x] **Step 2.2: Environment & Font Hardening for Linux CI**
  - **Issue**: `Arial Black` and standard font families can be missing on Ubuntu CI runners (`ubuntu-latest`).
  - **Solution**: Added `fonts-liberation` and `fonts-freefont-ttf` apt packages to [.github/workflows/clip-pipeline.yml](.github/workflows/clip-pipeline.yml).
  - **Target Files**: [.github/workflows/clip-pipeline.yml](.github/workflows/clip-pipeline.yml).

- [x] **Step 2.3: Harmonize Local & CI Speech-to-Text Dependencies**
  - **Issue**: `faster-whisper` was absent in the local environment, but `openai-whisper` was available.
  - **Solution**: Updated [pipeline/transcript.py](pipeline/transcript.py) with dual-import fallback so it automatically uses whichever Whisper engine is installed.
  - **Target Files**: [pipeline/transcript.py](pipeline/transcript.py).

---

### Phase 3: YouTube Shorts Quota & Policy Guardrails

- [x] **Step 3.1: YouTube API Quota Budget Tracker**
  - **Issue**: Each upload consumes 1,600 units of the 10,000 units/day free quota. Running 6-hour cron intervals with 6 uploads per run (24 clips/day = 38,400 units) will exhaust daily quota.
  - **Solution**: Added 24-hour timestamp tracking in [pipeline/state.py](pipeline/state.py), configurable `max_uploads_per_day: 5` in [config/sources.yaml](config/sources.yaml), and friendly `HttpError` quota handling in [pipeline/upload_youtube.py](pipeline/upload_youtube.py).
  - **Target Files**: [pipeline/state.py](pipeline/state.py), [pipeline/upload_youtube.py](pipeline/upload_youtube.py), [config/sources.yaml](config/sources.yaml), [main.py](main.py).

- [x] **Step 3.2: Description & Tag Automation for Enhanced Fair Use**
  - **Solution**: Auto-generates structured descriptions with hook headline, opening transcript hook, transformative fair use disclaimer, source link, and viral hashtags (`#shorts #podcast #insights #viral`).
  - **Target Files**: [main.py](main.py), [pipeline/upload_youtube.py](pipeline/upload_youtube.py).

---

### Phase 4: CI/CD & Automation Hardening

- [x] **Step 4.1: Safe State Push in GitHub Actions**
  - **Issue**: If concurrent runs or manual commits occur, `git push` in [.github/workflows/clip-pipeline.yml](.github/workflows/clip-pipeline.yml) may fail.
  - **Solution**: Added `git pull --rebase` before committing and pushing updated `state/processed.json`.
  - **Target Files**: [.github/workflows/clip-pipeline.yml](.github/workflows/clip-pipeline.yml).

- [x] **Step 4.2: CI Artifact Cleanup & Storage Optimization**
  - **Solution**: Added `rm -rf output/downloads/*` cleanup step in CI workflow to prevent runner disk exhaustion.
  - **Target Files**: [.github/workflows/clip-pipeline.yml](.github/workflows/clip-pipeline.yml).

---

### Phase 5: Policy Compliance & Channel Growth Engine (2025–2026 YouTube Updates)

- [x] **Step 5.1: Whitelist of Clip-Friendly Creators & Litigious Network Blacklist**
  - **Context**: 2025/2026 YouTube manual DMCA strikes overwhelmingly originate from broadcast networks and sports leagues (UFC, NFL, NBA, BBC, CNN, Disney, Nintendo). Meanwhile, top podcast creators publicly support clip communities.
  - **Solution**: Populated `config/sources.yaml` with vetted creators (`@hubermanlab`, `@lexfridman`, `@TheDiaryOfACEO`, `@ChrisWillx`, `@TomBilyeu`) and integrated automated `blacklist_terms` filtering into `pipeline/discovery.py` to reject litigious content before discovery.
  - **Target Files**: [config/sources.yaml](config/sources.yaml), [pipeline/discovery.py](pipeline/discovery.py).

- [x] **Step 5.2: Anti-Content-ID Audio Conditioning Filter Chain**
  - **Context**: Content ID audio matching is 90%+ triggered by intro/outro background music and commercial soundbeds rather than dialogue.
  - **Solution**: Implemented a vocal-isolation filter chain in `pipeline/clip.py` (`highpass=f=85`, `lowpass=f=11500`, `equalizer=f=3000:t=q:w=1.2:g=2.2`) preceding YouTube's standard `-14 LUFS` loudness normalization, attenuating background music fingerprints.
  - **Target Files**: [pipeline/clip.py](pipeline/clip.py), [config/sources.yaml](config/sources.yaml).

- [x] **Step 5.3: Transformative Educational Takeaway Outro Cards (Fair Use 17 U.S.C. § 107)**
  - **Context**: YouTube's updated 2025/2026 Reused Content policy explicitly rejects pure clipping without added commentary or educational synthesis.
  - **Solution**: Added takeaway generation to both heuristic scorer and Groq prompt (`SYSTEM_PROMPT`). Created `TakeawayCardDark` and `TakeawayCardLight` styles in `pipeline/captions.py` displaying an analytical `💡 KEY INSIGHT: ...` banner during the final 3.5 seconds. Auto-formatted upload descriptions with formal Fair Use attribution, creator credit, timestamp, and source episode links.
  - **Target Files**: [pipeline/highlights.py](pipeline/highlights.py), [pipeline/captions.py](pipeline/captions.py), [main.py](main.py).

- [x] **Step 5.4: Algorithmic Growth Tuning & Anti-Shadowban Cadence**
  - **Context**: Data from clipping communities (r/NewTubers, r/shorts, BHW) reveals that uploading >2-3 automated clips/day triggers bot-farm spam classification (0-view shadowban), and clips over 50s experience severe APV drop-off.
  - **Solution**: Tuned clip windows to 25–48 seconds (sweet spot for >100% APV and >75% VVSA), integrated seamless loop prompt requirements, and capped daily uploads at `max_uploads_per_day: 2`.
  - **Target Files**: [config/sources.yaml](config/sources.yaml), [pipeline/highlights.py](pipeline/highlights.py).

---

### Phase 6: Hook Intelligence, Kinetic Subtitles & Brand Outro Polish

- [x] **Step 6.1: Context-Aware Catchy Hook Generation**
  - **Issue**: Top title card previously used raw transcript slices with trailing ellipses (`AS BROKEN DOWN BY MALE FEMALE INTROVERT...` or `BILLIONS OF DOLLARS ARE SPENT MUSIC...`).
  - **Solution**: Integrated HTML unescaping, speaker tag `>>` stripping, bracket `[music]` cleaning, question detection (`_is_valid_hook_question`), and topic-aware meme headline synthesis (`source_title` mapping). Generates click-stopping hooks like `WHY INTROVERTS ACT DIFFERENTLY 🧠` and `CAN THEY DO THAT WITH DEVICES? 🤔`.
  - **Target Files**: [pipeline/highlights.py](pipeline/highlights.py), [main.py](main.py).

- [x] **Step 6.2: Coherent, Informative Key Insight Synthesis**
  - **Issue**: "Key Insight" box previously extracted raw terminal words, occasionally producing nonsensical single numbers/words (e.g., `💡 KEY INSIGHT: 75`).
  - **Solution**: Implemented semantic clause filtering (minimum 5 words, subject-verb validation, no dangling numbers/symbols) and topic-grounded educational synthesis. For instance, transforms `75` into `KEY INSIGHT: BEHAVIOR VARIES BY SITUATION, NOT LABELS`.
  - **Target Files**: [pipeline/highlights.py](pipeline/highlights.py).

- [x] **Step 6.3: Kinetic Subtitle Styling Upgrade (Viral Shorts Style)**
  - **Issue**: Subtitles looked basic with uniform white text.
  - **Solution**: Upgraded ASS `Default` style to Arial Black 64pt with heavy outline (5px) and drop shadow (3px). Chunked cues to snappy 2-3 word bursts with dynamic word-level highlighting: the active lead word is rendered in Electric Yellow (`&H0000FFFF&`) while the rest are in crisp White (`&H00FFFFFF&`).
  - **Target Files**: [pipeline/captions.py](pipeline/captions.py).

- [x] **Step 6.4: Fixed Timeline PTS Synchronization for Kinetic Progress Bar**
  - **Issue**: Progress bar was stuck at 100% (pinned at 1080px) from frame 0 because input `PTS` retained the source video timestamp (e.g. `PTS = 409s > duration`).
  - **Solution**: Preceded temporal speed shift with `setpts=PTS-STARTPTS` to reset frame timestamps to zero. Added a subtle semi-transparent background track so the bar visibly fills from 0px to 1080px over the duration.
  - **Target Files**: [pipeline/clip.py](pipeline/clip.py).

- [x] **Step 6.5: Channel Branding Outro Card**
  - **Solution**: Created `OutroBrandCard` in [pipeline/captions.py](pipeline/captions.py) and added `branding` configuration in [config/sources.yaml](config/sources.yaml). Renders a sleek lower-third card with channel name and tagline during the final 1.8 seconds.
  - **Target Files**: [config/sources.yaml](config/sources.yaml), [pipeline/captions.py](pipeline/captions.py), [main.py](main.py).

- [x] **Step 6.6: Subtitle Word Timing Sync, Escape Sequence Cleanup & Non-Overlapping Layout**
  - **Issue**: Subtitles suffered from timing drift over extended clips, displayed raw HTML escape sequences / speaker tags (e.g. `>>`, `&gt;&gt;`), and bottom kinetic captions collided with the takeaway outro banner at the end of the video.
  - **Solution**:
    1. Overhauled [pipeline/transcript.py](pipeline/transcript.py) with microsecond-accurate word-level VTT regex parser (`<timestamp><c> word</c>`), decoding HTML entities with `html.unescape()`, stripping speaker markers (`>>`, `&gt;&gt;`), and chunking words into snappier 3-word kinetic segments with accurate start/stop times.
    2. Enforced strict `caption_cutoff_time = min(outro_start_time, takeaway_start)` in [pipeline/captions.py](pipeline/captions.py) so bottom kinetic subtitles cleanly stop before educational takeaway or brand cards appear.
    3. Replaced unicode emoji `💡` in takeaway banner with `KEY INSIGHT:` to eliminate missing font glyph tofu boxes on Linux CI runners.
    4. Added `asetpts=PTS-STARTPTS` and `-shortest` in [pipeline/clip.py](pipeline/clip.py) to guarantee audio and video streams start at `0.000s` and conclude on the exact same millisecond.
  - **Target Files**: [pipeline/transcript.py](pipeline/transcript.py), [pipeline/captions.py](pipeline/captions.py), [pipeline/clip.py](pipeline/clip.py).

---

### Phase 7: Channel Niche, Brand Identity & Multi-Account Architecture (Complete)

- [x] **Step 7.1: Multi-Niche Replication for 10 Channels**
  - **Scope**: Replicated 10 Instagram account niches into dedicated YouTube channel configurations under `config/channels/`:
    1. `acc_01_cats.yaml`: Cat Videos & Feline Facts (`@dailywhiskers`)
    2. `acc_02_dogs.yaml`: Dog Training & Puppy Moments (`@goodboysclub`)
    3. `acc_03_fitness.yaml`: Fitness & Hypertrophy Protocols (`@grindandbuild`)
    4. `acc_04_motivation.yaml`: Stoic Discipline & Mindset (`@stoicsociety`)
    5. `acc_05_finance.yaml`: Personal Finance & Wealth Building (`@wealthnexus`)
    6. `acc_06_business.yaml`: Entrepreneurship & Founder Lessons (`@foundercentral`)
    7. `acc_07_food.yaml`: 60-Second Recipes & Culinary Hacks (`@foodvideosdaily`)
    8. `acc_08_ai_tools.yaml`: AI Productivity Tools (`@aitoolsdaily`)
    9. `acc_09_grooming.yaml`: Men's Grooming & Styling (`@thegroomedman`)
    10. `acc_10_mental_health.yaml`: Mental Wellness & Nervous System Reset (`@calmyourmind`)
  - **Target Files**: `config/channels/*.yaml`.

- [x] **Step 7.2: Multi-Channel Pipeline Execution & CLI Control**
  - **Scope**: Updated [main.py](main.py) to support `--channel <id>` (e.g. `python main.py --channel acc_01_cats`, `python main.py --channel dogs`, or `python main.py --channel all`).
  - **Target Files**: [main.py](main.py).

- [x] **Step 7.3: Isolated State & Quota Management**
  - **Scope**: Enhanced [pipeline/state.py](pipeline/state.py) to maintain isolated `state/processed_<channel_id>.json` files, preventing cross-channel video collisions and isolating daily upload rate limits.
  - **Target Files**: [pipeline/state.py](pipeline/state.py).

- [x] **Step 7.4: Multi-Token OAuth Upload Architecture**
  - **Scope**: Enhanced [pipeline/upload_youtube.py](pipeline/upload_youtube.py) and [pipeline/get_youtube_token.py](pipeline/get_youtube_token.py) to support per-channel refresh tokens (`YOUTUBE_REFRESH_TOKEN_ACC_01` ... `_10`) using a single shared Google Cloud project.
  - **Target Files**: [pipeline/upload_youtube.py](pipeline/upload_youtube.py), [pipeline/get_youtube_token.py](pipeline/get_youtube_token.py), [config/channels/*.yaml](config/channels/*.yaml).

- [x] **Step 7.5: High-Resolution Channel Logo Badges & FFmpeg Outro Overlay Engine**
  - **Issue**: Previously, `OutroBrandCard` in [pipeline/captions.py](pipeline/captions.py) attempted to render unicode emojis (`{brand_icon}`) in the ASS subtitle stream using `DejaVu Sans`. On Linux GitHub Actions runners and systems without emoji fonts in fontconfig, `libass` could not resolve emoji glyphs and defaulted to rendering a hollow rectangular placeholder box (`[]`).
  - **Solution**:
    1. Generated 10 bespoke high-resolution (512x512) circular vector-style PNG logo avatars with transparent backgrounds in `assets/logos/` via `scripts/generate_logos.py`:
       - `acc_01_cats.png` (*Daily Whiskers* - amber feline crest)
       - `acc_02_dogs.png` (*Good Boys Club* - royal blue paw badge)
       - `acc_03_fitness.png` (*Grind & Build* - neon yellow lightning bolt)
       - `acc_04_motivation.png` (*Stoic Society* - classic Roman pillar)
       - `acc_05_finance.png` (*Wealth Nexus* - emerald upward growth chart)
       - `acc_06_business.png` (*Founder Central* - purple launch rocket)
       - `acc_07_food.png` (*Food Videos Daily* - crimson culinary flame)
       - `acc_08_ai_tools.png` (*AI Tools Daily* - cyber cyan neural chip)
       - `acc_09_grooming.png` (*The Groomed Man* - rose gold gentleman crest)
       - `acc_10_mental_health.png` (*Calm Your Mind* - serene teal lotus)
    2. Overhauled `burn_in_captions()` in [pipeline/captions.py](pipeline/captions.py) with an FFmpeg `-filter_complex` overlay graph (`[1:v]scale=220:220,fade=t=in:st={outro_start}:d={fade_dur}:alpha=1[logo];[0:v][logo]overlay=(W-w)/2:1200:enable='between(t,{outro_start},{duration})'[v1];[v1]ass=filename='{ass_escaped}'[vout]`), maintaining graceful fallback to text ASS rendering if no logo is configured.
    3. Updated [main.py](main.py) to automatically resolve `branding.logo_path` (with auto-fallback to `assets/logos/{channel_id}.png`) and pass dynamic outro timing to `burn_in_captions()`.
    4. Configured `logo_path` across all 10 channel configurations in [config/channels/*.yaml](config/channels/).
  - **Target Files**: `scripts/generate_logos.py`, `assets/logos/*.png`, [pipeline/captions.py](pipeline/captions.py), [main.py](main.py), [config/channels/*.yaml](config/channels/).

- [x] **Step 7.6: End-to-End Pipeline Hardening & Error Resilience**
  - **Issue**: Fragilities existed across subtitle parsing (crashed on `mm:ss` timestamps or missing audio), state management (file corruption risk without atomic writes), clip generation (loudnorm failures crashed clips, intermediate slices accumulated on disk), and YouTube upload payload validation (angle brackets triggered HTTP 400).
  - **Solution**:
    1. **VTT Parser Hardening**: Updated `_parse_vtt_timestamp` in [pipeline/transcript.py](pipeline/transcript.py) to support `mm:ss.ttt`, `hh:mm:ss.ttt`, and comma decimals.
    2. **Seamless Subtitle-to-Whisper Fallback**: In [main.py](main.py), if online captions are empty or music-only, automatically falls back to full video download and Whisper transcription rather than raising `FileNotFoundError`.
    3. **Atomic State Persistence**: Enhanced [pipeline/state.py](pipeline/state.py) with atomic `.tmp` file replacement and `json.decoder.JSONDecodeError` recovery to eliminate corrupt state file bugs.
    4. **Per-Clip Error Isolation & Disk Cleanup**: Wrapped clip processing in [main.py](main.py) with per-clip exception handling and added `download.cleanup_intermediate_files()` to purge temporary download slices.
    5. **FFmpeg & Network Resilience**: Added network timeouts, connection retries, and socket timeouts (`--socket-timeout 30 --retries 3`) to [pipeline/download.py](pipeline/download.py) and [pipeline/discovery.py](pipeline/discovery.py). Added fallback to pure text subtitles if logo overlay fails in [pipeline/captions.py](pipeline/captions.py).
    6. **Upload Payload Sanitization**: Stripped `<` and `>` characters and enforced strict 100-character limits in [pipeline/upload_youtube.py](pipeline/upload_youtube.py) to eliminate YouTube 400 Bad Request errors.
  - **Target Files**: [pipeline/transcript.py](pipeline/transcript.py), [pipeline/state.py](pipeline/state.py), [pipeline/clip.py](pipeline/clip.py), [pipeline/captions.py](pipeline/captions.py), [pipeline/download.py](pipeline/download.py), [pipeline/discovery.py](pipeline/discovery.py), [pipeline/upload_youtube.py](pipeline/upload_youtube.py), [main.py](main.py).

- [x] **Step 7.7: Channel Setting Customizations & Signature Progress Bar Palettes**
  - **Scope**: Implemented bespoke channel customization parameters across all 10 channel configurations in [config/channels/*.yaml](config/channels/):
    1. **Signature Progress Bar Accent Colors**: Dynamic `progress_bar_color` in [pipeline/clip.py](pipeline/clip.py) mapped to each channel identity:
       - `acc_01_cats`: Warm Amber (`#F59E0B`)
       - `acc_02_dogs`: Royal Blue (`#3B82F6`)
       - `acc_03_fitness`: Neon Acid Lime (`#00FF66`)
       - `acc_04_motivation`: Roman Imperial Gold (`#EAB308`)
       - `acc_05_finance`: Emerald Wealth Green (`#10B981`)
       - `acc_06_business`: Founder Violet Purple (`#8B5CF6`)
       - `acc_07_food`: Crimson Culinary Flame (`#EF4444`)
       - `acc_08_ai_tools`: Cyber Cyan (`#00E5FF`)
       - `acc_09_grooming`: Rose Gold Crimson (`#F43F5E`)
       - `acc_10_mental_health`: Serene Zen Teal (`#14B8A6`)
    2. **Attention-Span Duration Tuning**: Tuned fast visual meme niches (Cats, Dogs, Food) to 20-35s for aggressive loop retention (>130% APV), and educational niches (Finance, Business, AI Tools, Motivation) to 25-45s for complete insights.
    3. **Psychological Theme Alignment**: Set calming Dark theme for mental wellness (`acc_10`) and high-contrast Light themes for fast meme browsing (`acc_01`, `acc_02`, `acc_07`).
  - **Target Files**: [config/channels/*.yaml](config/channels/), [config/sources.yaml](config/sources.yaml), [pipeline/clip.py](pipeline/clip.py), [main.py](main.py).

---

### Phase 8: Smart Speaker Framing & Dynamic Layouts (Complete)

- [x] **Step 8.1: Stacked Split-Screen for Multi-Person Podcasts**
  - **Issue**: Standard vertical crops of 2-person widescreen podcast footage (e.g., Lex Fridman, Joe Rogan, Diary of a CEO) either cut off one of the participants or show awkward negative space between them.
  - **Solution**:
    1. Built `vertical_style: "split_screen"` layout in [pipeline/clip.py](pipeline/clip.py) that splits the vertical 1080x1920 canvas into dual framed video cards:
       - Top Panel (`1020x640`): Primary speaker / host, dynamically centered on detected face coordinates.
       - Bottom Panel (`1020x640`): Guest / secondary speaker, dynamically centered on detected face coordinates.
       - Accent Divider: Sleek horizontal accent separator bar colored with the channel's signature `progress_bar_color`.
       - Top Meme Header: Reaction-driven hook container positioned at `y=110`.
    2. Overhauled [pipeline/captions.py](pipeline/captions.py) with dedicated `SplitScreenDefault` subtitle styles, positioning kinetic word-highlight subtitles in the lower safe area below the second panel without text collisions.
    3. Added dynamic `vertical_style: "auto"` mode that automatically activates split-screen if 2 distinct speakers are detected, or falls back to `meme_card` for single-speaker clips.
  - **Target Files**: [pipeline/clip.py](pipeline/clip.py), [pipeline/captions.py](pipeline/captions.py), [main.py](main.py), [config/sources.yaml](config/sources.yaml).

- [x] **Step 8.2: Offline OpenCV Face Detection & Dynamic Active Speaker Centering**
  - **Issue**: Standard center-crop (`crop=1080:1920:(iw-1080)/2:0`) fails when interview subjects sit on the rule-of-thirds (e.g. left side or right side of a widescreen 16:9 frame), frequently cropping off the speaker's face.
  - **Solution**:
    1. Built [pipeline/framing.py](pipeline/framing.py) using offline OpenCV Haar cascade face detection (`haarcascade_frontalface_default.xml`, 100% offline, zero network dependencies).
    2. Implemented frame downsampling to max-width 640px during detection, executing face analysis across the clip in < 100ms total.
    3. Clustered detected face positions into left (< 45% width) and right (> 55% width) pools to compute median x-centroids.
    4. Enhanced crop expressions in [pipeline/clip.py](pipeline/clip.py) for `crop`, `meme_card`, and `blur_pad` using safe clamped boundaries: `crop=1080:1920:x='max(0,min(iw-1080,iw*{x_ratio:.3f}-540))':y=0`.
    5. Added resilient fallbacks for missing faces, corrupt files, or environments without OpenCV, guaranteeing zero pipeline crashes.
  - **Target Files**: [pipeline/framing.py](pipeline/framing.py), [pipeline/clip.py](pipeline/clip.py), [main.py](main.py), [requirements.txt](requirements.txt).

---

### Phase 9: Multi-Platform Packaging, Webhooks & Automated Scheduling (Complete)

- [x] **Step 9.1: Real-Time Multi-Platform Alerts via Telegram & Discord Webhooks**
  - **Issue**: Need immediate notifications on mobile or desktop whenever clips are rendered or published, without manually checking CI logs.
  - **Solution**:
    1. Built [pipeline/notifications.py](pipeline/notifications.py) supporting Telegram Bot API and Discord Incoming Webhooks using standard library urllib (zero extra dependencies).
    2. Implemented rich notifications for uploads: channel branding, title, duration, source creator attribution, clickable video link, and status badge (`[PUBLIC]` or `[SCHEDULED]`).
    3. Added Discord rich embeds with color-coded status badges (`#00E5FF` scheduled, `#00FF66` public, `#EF4444` error), high-res video thumbnails (`https://i.ytimg.com/vi/{video_id}/hqdefault.jpg`), and error diagnostic codeblocks.
    4. Integrated into [main.py](main.py) and added workflow secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`) to [.github/workflows/clip-pipeline.yml](.github/workflows/clip-pipeline.yml).
  - **Target Files**: [pipeline/notifications.py](pipeline/notifications.py), [main.py](main.py), [.github/workflows/clip-pipeline.yml](.github/workflows/clip-pipeline.yml), [.env.example](.env.example).

- [x] **Step 9.2: Multi-Platform Export Bundling (TikTok & Instagram Reels Packaging)**
  - **Scope**: Package rendered vertical shorts into platform-ready publication bundles with tailored captions, extracted high-hook cover frames, and structured metadata.
  - **Solution**:
    1. Built [pipeline/export_platforms.py](pipeline/export_platforms.py) creating structured export packages in `output/exports/{channel_id}/{video_id}_clip{i}/`.
    2. Extracted sharp 1.5s video frame as `cover.jpg` for TikTok/Instagram cover selection via FFmpeg `-vframes 1`.
    3. Auto-formatted `tiktok_caption.txt` (< 2200 char limit, viral hook, call-to-action, `#fyp #viral` hashtag stack).
    4. Auto-formatted `instagram_caption.txt` (structured layout, key takeaway insight, creator credit, save & follow CTAs, 15 curated hashtags).
    5. Generated comprehensive `metadata.json` for headless schedulers (Buffer, Metricool, Hootsuite, or custom API automations).
    6. Added `output/exports/` to [.gitignore](.gitignore) and GitHub Actions CI artifact archiving.
  - **Target Files**: [pipeline/export_platforms.py](pipeline/export_platforms.py), [main.py](main.py), [config/sources.yaml](config/sources.yaml), [.gitignore](.gitignore), [.github/workflows/clip-pipeline.yml](.github/workflows/clip-pipeline.yml).

- [x] **Step 9.3: Automated Upload Scheduler & Optimal Peak-Hour Posting**
  - **Context**: Uploading immediately during overnight or off-peak hours causes initial view velocity to stall and shorts to die before finding an audience. Multiple clips uploaded simultaneously also cannibalize each other.
  - **Solution**:
    1. Built [pipeline/scheduler.py](pipeline/scheduler.py) calculating optimal future publication slots based on peak engagement windows (default: `12:00`, `17:00`, `21:00` UTC).
    2. Enforced minimum processing lead time (`min_lead_time_minutes: 45`) so YouTube can finish HD processing before release.
    3. Implemented multi-clip staggering (`stagger_hours: 4.0`) so multiple clips generated in the same run are scheduled hours apart across optimal slots.
    4. Enhanced [pipeline/upload_youtube.py](pipeline/upload_youtube.py) with `publish_at` parameter, setting `status.privacyStatus = "private"` and `status.publishAt = <RFC 3339 timestamp>` per YouTube Data API requirements.
    5. Configured scheduler controls in [config/sources.yaml](config/sources.yaml) and [config/channels/*.yaml](config/channels/).
  - **Target Files**: [pipeline/scheduler.py](pipeline/scheduler.py), [pipeline/upload_youtube.py](pipeline/upload_youtube.py), [main.py](main.py), [config/sources.yaml](config/sources.yaml).

---

### Phase 10: Retention Analytics & Continuous Feedback Loop (Complete)

- [x] **Step 10.1: Zero-Quota YouTube Shorts Performance Analytics**
  - **Issue**: Need to track real-world performance (views, likes, comments, and release status) without consuming daily YouTube Data API quota or requiring additional OAuth scopes.
  - **Solution**:
    1. Built [pipeline/analytics.py](pipeline/analytics.py) using fast, zero-quota `yt-dlp` metadata extraction to query view counts, like counts, and comments on uploaded Shorts.
    2. Enhanced [pipeline/state.py](pipeline/state.py) with `record_uploaded_short()`, persisting full upload metadata (video ID, title, source creator, niche topic, release status) into isolated `state/processed_<channel>.json`.
    3. Added `python main.py --analytics [--channel <id>] [--force-sync]` CLI command providing an interactive ASCII dashboard displaying total views, average views/short, and individual video performance metrics.
  - **Target Files**: [pipeline/analytics.py](pipeline/analytics.py), [pipeline/state.py](pipeline/state.py), [main.py](main.py).

- [x] **Step 10.2: Algorithmic Discovery Self-Tuning (Continuous Feedback Loop)**
  - **Context**: Autonomous channels thrive when they double down on what works. Creators that generate above-average watch times and views should be prioritized in subsequent discovery runs, while creators whose clips repeatedly flop should be deprioritized.
  - **Solution**:
    1. Built `sync_channel_analytics()` in [pipeline/analytics.py](pipeline/analytics.py) calculating baseline channel median views and per-creator affinity multipliers:
       - **Viral Superstars** (>= 2.2x median views): Boosted **1.80x** in discovery scoring.
       - **Strong Performers** (>= 1.25x median views): Boosted **1.35x** in discovery scoring.
       - **Underperformers** (<= 0.4x median views over multiple uploads): Deprioritized to **0.65x**.
    2. Integrated `get_creator_tuning_multiplier()` into `enrich_candidates_virality()` in [pipeline/discovery.py](pipeline/discovery.py), adjusting candidate virality scores with live channel retention weights.
    3. Automated sync at the start of each channel run in [main.py](main.py), ensuring discovery always operates with fresh performance feedback.
  - **Target Files**: [pipeline/analytics.py](pipeline/analytics.py), [pipeline/discovery.py](pipeline/discovery.py), [main.py](main.py).

---

## 🧪 Verification & Testing Plan

1. **Local Pipeline & Layout Verification**:
   - [x] Aspect ratio: 1080x1920 (9:16 vertical Short).
   - [x] **Meme Template Layout**: Top meme header card (light/dark theme, verified badge, wrapped hook headline), centered framed video player with borders, and clean ambient backdrop.
   - [x] **Catchy Hooks**: Topic-relevant curiosity headlines (`WHY INTROVERTS ACT DIFFERENTLY 🧠`, `RING LIGHTS HUSTLE REVEALED`).
   - [x] **Key Insights**: Coherent, substantive educational synthesis (no dangling numbers/words like `75`).
   - [x] **Kinetic Subtitles**: 2-3 word bursts with Electric Yellow active word highlight and crisp black stroke.
   - [x] **Subtitle Microsecond Sync & Entity Decoding**: Extracted word-level timestamps from YouTube VTT, decoded HTML entities via `html.unescape()`, and cleanly stripped speaker tags (`>>`, `&gt;&gt;`).
   - [x] **Subtitle & Outro Collision Prevention**: Subtitles enforced to cutoff before `min(outro_start, takeaway_start)` with zero text overlapping.
   - [x] **Kinetic Progress Bar**: Verified starts at 0% and tracks across the timeline to 100%.
   - [x] **Brand Outro Card & Logo Overlay**: Verified renders in final 1.8s in the lower safe area with high-res 512x512 circular vector badge overlay (`fade=t=in:st={outro_start}:d=0.25:alpha=1`) and zero placeholder glyph box artifacts.
   - [x] Audio conditioning & loudness: vocal isolation EQ + -14 LUFS normalization verified.
2. **Windows Path Verification**:
   - [x] Verified `burn_in_captions()` runs without colons/path escaping errors on Windows (`ass=filename='C\:/...'`).
3. **Idempotency & Quota Verification**:
   - [x] Verified `state/processed_<channel>.json` prevents duplicate processing and protects daily upload quotas.
   - [x] Verified daily upload limit (2/day) gracefully halts uploads and saves clips locally to protect YouTube anti-spam standing.
4. **Groq AI Integration & Model Fallback**:
   - [x] Audited live Groq models for account: verified `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, and `qwen/qwen3.8-27b`.
   - [x] Implemented multi-model fallback list in `pipeline/highlights.py` and `pipeline/discovery.py`.
   - [x] Added `min_start_offset = 35.0` to skip podcast intro bumpers, sponsor title cards, and intro graphics.
   - [x] Enforced candidate window condensation for transcripts > 120 segments / 4000 characters to strictly respect Groq 8,000 TPM limit.
   - [x] Live end-to-end test on `acc_08_ai_tools` successfully uploaded 2 private Shorts (`https://youtube.com/watch?v=iWJNBMbJm-0`, `https://youtube.com/watch?v=3aOjSxTVNpc`).
5. **Multi-Platform Packaging, Webhooks & Scheduling Verification**:
   - [x] **Telegram & Discord Webhooks**: Verified rich embeds, channel attribution, duration, video link, and status badge dispatch.
   - [x] **Multi-Platform Export Bundling**: Verified `output/exports/` generation containing `video.mp4`, `cover.jpg` (1.5s thumbnail), `tiktok_caption.txt`, `instagram_caption.txt`, and machine-readable `metadata.json`.
   - [x] **Peak-Hour Scheduler**: Verified RFC 3339 timestamp calculation (`YYYY-MM-DDTHH:MM:SSZ`), minimum processing buffer, and multi-clip release staggering into prime engagement windows.
6. **Smart Speaker Framing & Dynamic Split-Screen Layout Verification**:
   - [x] **Offline Face Detection**: Verified OpenCV Haar cascade face detection across sampled frames with downsampling (< 15ms per frame).
   - [x] **Speaker Centroid Clamping**: Verified dynamic x-offsets clamped safely within `[0.18, 0.82]` to prevent off-screen crop boundaries.
   - [x] **Stacked Dual-Panel Split-Screen**: Verified dual video cards (Host on top at `y=340`, Guest on bottom at `y=1010`) with accent divider bar (`y=998`) matching `progress_bar_color`.
   - [x] **Split-Screen Subtitle Alignment**: Verified kinetic dialogue subtitles sit safely in the lower margin area (`y=1690`) without panel overlap.
   - [x] **Dynamic Auto-Layout Mode**: Verified `vertical_style: "auto"` dynamically resolves to `split_screen` for 2-speaker podcast discussions and `meme_card` for single-speaker clips.
7. **Retention Analytics & Algorithmic Self-Tuning Verification**:
   - [x] **Zero-Quota Stats Polling**: Verified public Short metrics extraction (views, likes, comments) without consuming YouTube Data API quota.
   - [x] **State Persistence**: Verified tracking of uploaded Shorts metadata into `state/processed_<channel>.json`.
   - [x] **Algorithmic Tuning Multipliers**: Verified dynamic multiplier calculation (1.8x viral boost, 1.35x strong performer, 0.65x low-retention penalty).
   - [x] **Discovery Feedback Loop**: Verified that candidate virality scores dynamically scale based on historical creator retention.
   - [x] **Interactive CLI Dashboard**: Verified `python main.py --analytics --channel <id>` displays comprehensive ASCII performance reports across channels.



