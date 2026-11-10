# YouTube Clipping Pipeline — Bug-Fix & Regression Prevention Log

> **Rule for Future Fixes:** Before editing `.github/workflows/clip-pipeline.yml`, `main.py`, or any module in `pipeline/`, check the **Critical Invariants ("Do Not Undo")** section below. Every item listed here fixed a real CI failure and must **not** be reverted or bypassed when solving a new issue.

---

## Critical Invariants (Do Not Undo)

### 1. Cloudflare WARP & YouTube Egress Guard (`.github/workflows/clip-pipeline.yml`)
- **Runner stagger + non-fatal WARP setup (`8557ac5`, `c7bc233`)**: Keep `sleep $((RANDOM % 25 + 1))` before WARP setup and `timeout-minutes: 1` + `continue-on-error: true` on `fscarmen/warp-on-actions@v1.4` so an unresponsive default endpoint never hangs a job until cancellation.
- **Multi-stage egress recovery (`c7bc233`, `720175e`, `c584c29`, `abc3961`)**:
  - **Stage A:** Rotate alternate Cloudflare `:2408` WireGuard endpoints, tracking all flagged IPv4s in **`BAD_V4_IPS` (`add_bad_ip` / `is_bad_ip`)** (never overwrite a single `BAD_V4_IP` variable; Run `42853492089` proved multiple `:2408` endpoints can bounce between bad/previously-tested IPs or hit the same shared PoP CGNAT IPv4).
  - **Stage B (Fast Unique IPv6):** Route dual-stack egress through the runner's unique `/128` Cloudflare WARP IPv6 (`2a09:bac5:...`) via `/etc/gai.conf` (`fc00::/7` ULA label/precedence matched with `::/0`) and copy `/etc/gai.conf` into `bgutil-provider` + restart it.
  - **Stage C (`warp-cli` Fallback):** Fresh registration with official `cloudflare-warp` (`MASQUE` + `MASQUE IPv6` + `WireGuard`), restoring WireGuard `warp` afterwards if all probes fail so traffic stays behind WARP instead of falling back to flagged raw Azure IPs.
- **Root-permission requirement (`abc3961`)**: `/etc/wireguard/` is `0700 root:root`. **Always** use `sudo test -f /etc/wireguard/warp.conf` and `sudo grep ... /etc/wireguard/warp.conf` — plain `[ -f /etc/wireguard/warp.conf ]` evaluates `false` as `runner`, which silently skipped Stage B IPv6 and WireGuard restoration in Run `42857059763`.
- **Restore `WORKING_EP` before Stage B (`abc3961`)**: Stage A may end on an unresponsive endpoint (e.g. `162.159.198.1:2408`). Always preserve the last responsive endpoint in `WORKING_EP` (or bounce `wg-quick`) before running Stage B's `curl -6` trace.
- **2-video YouTube probe in `check_yt_player()` (`c584c29`)**: Always validate **both** real `.vtt` timedtext download on `M7lc1UVf-VE` (`visionos,ios,mweb`) and format/player extraction on `Ks-_Mh1QhMc` (`android_vr,mweb,web`). A single `-s --print "%(id)s"` check on `jNQXAC9IVRw` produced false positives (`104.28.210.137` in Run `42853492089`). Keep `timeout >= 24s` on Probe 1 so cold `bgutil-provider` IntegrityToken minting doesn't time out.

### 2. Anonymous-First Extraction, Cookie Fallback & Cooldown (`pipeline/download.py`, `pipeline/discovery.py`)
- **Anonymous-first requests (`2ba610f`)**: Run `yt-dlp` with `ignore_cookies=True` by default across discovery enrichment, subtitles, audio, and clip sections so 10 parallel jobs do not burn shared session cookies.
- **Filter `visionos`/`ios` when using cookies (`720175e`)**: Always pass `_cookie_compatible_clients()` (`mweb,web,tv`) whenever `--cookies` is attached; `yt-dlp` skips `visionos` and `ios` under cookies.
- **Validate actual output on `rc=0` (`720175e`)**: Keep `success_validator` in `_run_ytdlp_resilient()` and `download_subtitles()`. With `--ignore-no-formats-error`, `yt-dlp` can exit `0` even after printing `WARNING: Sign in to confirm` or `HTTP Error 429`; without checking that a valid `.vtt` file actually exists, cookie/429 fallbacks are skipped.
- **Precise error matching (`ba1e716`, `720175e`)**: Use regex word boundaries/specific phrases (`_is_http_429`, `_needs_auth_fallback`, `_is_session_rate_limited`) — never match bare `"429"`, `"bot"`, or `"available"` substrings against arbitrary video IDs/titles.
- **Sticky session rate-limit cooldown (`2ba610f`)**: If cookies trigger `"session has been rate-limited"` / `"content isn't available, try again later"`, call `disable_session_cookies()` and recover anonymously (`get_cookies_path()` returns `None` for the rest of the run).

### 3. State-Poisoning & Discovery Accuracy (`pipeline/discovery.py`, `main.py`, `pipeline/state.py`)
- **Never mark blocked/rate-limited videos processed (`0168e24`, `8557ac5`, `ba1e716`)**: When `_LAST_SUBTITLE_ERROR` is `"bot"` or `"429"` (and bounded Whisper fallback fails), or when long videos (>30m) fail with `metadata_fetched=False`, `process_video()` **must raise** so `main.py` leaves the video out of `state/processed_<channel>.json`.
- **Full player metadata + language filtering (`ba1e716`)**: Verify `_has_full_player_info()` before trusting flat discovery entries, and demote non-English original audio (`*-orig` track check) so non-English dubs don't waste Whisper/render cycles.
- **Safe CI state push (`8557ac5`, `720175e`)**: Keep `concurrency.cancel-in-progress: false` and `git rebase --abort 2>/dev/null || true` inside the 8-attempt push retry loop in `.github/workflows/clip-pipeline.yml`.

### 4. Rendered Clip Stream & Upload Safety (`pipeline/download.py`, `pipeline/clip.py`, `pipeline/captions.py`, `pipeline/upload_youtube.py`)
- **Exclude VP9 Premium `616` & reject audio-only MP4s (`0168e24`)**: `download_clip_section()` excludes `format_id!=616`, verifies `_has_video_stream()`, and `cut_clip()`, `burn_in_captions()`, and `validate_video_file()` all enforce valid `1080x1920` video + audio streams.
- **Channel OAuth project isolation, token stripping & zero-quota pre-flight (`70526fb`, `150f930`, `7f04eed`, Phase B)**: Always pass `channel_config` into `upload_short()`, resolve P1 (`acc_01..03`) / P2 (`acc_04..06`) / P3 (`acc_07..10`) credentials via `_resolve_credentials_with_project()`, `.strip()` tokens/client credentials, and run `preflight_credentials()` upfront via `creds.refresh()` (0 YouTube Data API quota) before heavy downloads/Whisper so `invalid_grant` or missing secrets fail fast with secrets scrubbed (`_sanitize_auth_text`).

### 5. CI Observability & Failure Diagnostics (`scripts/write_job_summary.py`, `scripts/send_failure_summary.py`, `.github/workflows/clip-pipeline.yml`)
- **Per-job `$GITHUB_STEP_SUMMARY` + `WARP_EGRESS_*` env export**: `Verify & Guard WARP Tunnel` records `WARP_EGRESS_PATH` & `WARP_EGRESS_IP` via `record_warp_env()` on every branch; `write_job_summary.py` (`if: always()`) always emits a clean Markdown summary table and `output/run_summary_<channel>.json`.
- **Zero-dependency consolidated failure alerts**: `pipeline/notifications.py` keeps `dotenv` import optional so `notify_failure` (`needs: [setup, clip]`, `if: always() && ...`) runs cleanly without `pip install -r requirements.txt` and dispatches one consolidated Telegram/Discord summary + `::error::` annotations on partial/total failures.

---

## Bug-Fix & CI Run Ledger

| Date (UTC) | Commit / Run | Scope & Symptom | Root Cause Found | Fix Applied | Verified Result |
|---|---|---|---|---|---|
| 2026-11-08 | `7f04eed`, `0168e24`, `8557ac5` | WARP stalls (35m timeouts), subtitle HTTP 429s, audio-only VP9 `616` clips, state poisoning on blocked runs | Default WARP stall hung `apt`/`curl`; no subtitle 429 retry/Whisper cap; `format_id 616` wrote audio-only sections; exceptions caught & marked processed | Bounded timeouts + WARP stagger; `429` retry + Whisper cap; excluded `616` + `_has_video_stream` checks; preserved state on bot/429 errors | Eliminated hangs & audio-only clips |
| 2026-11-09 | `ba1e716` | Non-English dubbed videos selected; false error matches on `"429"` in IDs; discovery trusting flat search | Flat entries lacked `formats`/`subtitles` check; no `*-orig` language inspection; substring error checks | Added `_has_full_player_info`, `*-orig` demotion, regex error checks, bounded `download_audio_only` fallback | Local unit & E2E verification passed |
| 2026-11-10 | `2ba610f`, `c7bc233` | Parallel runners triggered 1-hour YouTube cookie session limit (`content isn't available`) + single-endpoint WARP stalls | Cookies sent first on all 10 jobs simultaneously; single WARP endpoint had no rotation | Anonymous-first `yt-dlp` default + sticky `disable_session_cookies()` cooldown; Stage A `:2408` + Stage C `warp-cli` recovery | Eliminated shared cookie burn |
| 2026-11-10 | `720175e` / Run `42853492089` | Cookie fallback never triggered on `--ignore-no-formats-error`; `acc_07_food` (`104.28.210.137`) bot-blocked after probe passed | `rc=0` with warning skipped fallback + `visionos,ios` incompatible with cookies; single `jNQXAC9IVRw` probe false-passed; `BAD_V4_IP` overwritten | Added `success_validator` + `_cookie_compatible_clients()`; drafted multi-IP blacklist + 2-video probe + IPv6 fallback | **9/10 passed** in Run `42853492089` (only `acc_07_food` failed on `104.28.210.137`) |
| 2026-11-10 | `c584c29` / Run `42857059763` | `acc_04_motivation`, `acc_07_food` (`eastus2`, `104.28.210.137`) & `acc_10_mental_health` (`westcentralus`, `104.28.221.80`) failed & dropped to raw Azure IPs | `[ -f /etc/wireguard/warp.conf ]` ran as `runner` on `0700 root:root` `/etc/wireguard/`, returning `false`, skipping Stage B (`2a09:bac5:...` IPv6) & preventing `wg-quick up warp` restore | Verified `check_yt_player()` accurately caught flagged IPs (`acc_08` recovered via Stage A; 7/7 probe-passing jobs had 0 bot errors); diagnosed root-perm bug + confirmed every runner has unique `2a09:bac5:...` IPv6 | **7/10 passed**; 0 poisoned IDs across all 3 failed states |
| 2026-11-10 | `abc3961` / Run `42860655949` | Fix Stage B (`2a09:bac5:...` IPv6) skipped + dead-endpoint carryover from Stage A | `/etc/wireguard/warp.conf` checks lacked `sudo`; Stage A ended on unresponsive `162.159.198.1:2408` before Stage B | Switched all `/etc/wireguard/warp.conf` checks/`grep` to `sudo`; saved/restored `WORKING_EP` before Stage B; added Stage C MASQUE IPv6 & `[yt-probe]` failure reason logging | **10/10 Passed** (`42860655949`: all 10 artifacts rendered cleanly; Stage A `acc_02`, Stage B IPv6 `acc_04`/`acc_07`, Stage C MASQUE IPv6 `acc_09` verified live) |
| 2026-11-10 | `d1f4f84` / Run `42864681361` | Silent OAuth expiry discovered late after 15m renders; generic `exit code 1` CI UI; noisy partial failure alerts | Uploads deferred auth check until final step; no structured `$GITHUB_STEP_SUMMARY` or consolidated failure job | Added 0-quota `preflight_credentials()`, sanitized `run_summary_<ch>.json`, `write_job_summary.py`, `send_failure_summary.py`, and `notify_failure` job | **10/10 Passed** (`42864681361`: 36 clips rendered, 10/10 OAuth tokens verified P1/P2/P3 at 0 quota, 10/10 `status-*` + `$GITHUB_STEP_SUMMARY` emitted, Stage B `acc_10` + Stage C MASQUE IPv6 `acc_03` recovered) |

---

## Phase B Rollout Status

1. [x] Per-job `$GITHUB_STEP_SUMMARY` Markdown status table + `::error::` annotations in [`.github/workflows/clip-pipeline.yml`](.github/workflows/clip-pipeline.yml) and [`scripts/write_job_summary.py`](scripts/write_job_summary.py).
2. [x] Zero-quota OAuth credential pre-flight (`preflight_credentials()` via `creds.refresh(Request())`) upfront in [`pipeline/upload_youtube.py`](pipeline/upload_youtube.py) and [`main.py`](main.py).
3. [x] Consolidated workflow-level failure notification job (`notify_failure`) + [`scripts/send_failure_summary.py`](scripts/send_failure_summary.py).
4. [x] Local verification (Phase A + Phase B suites), state rebase sync, push, and live 10/10 CI validation (Run `42864681361`).

