import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "output" / "downloads"


_COOKIE_LOGGED = False


def get_cookies_path() -> Path | None:
    """Finds or creates a valid cookies file from environment secrets or workspace files."""
    global _COOKIE_LOGGED
    cookie_file = None

    # 1. Direct explicit environment path
    env_path = os.environ.get("YOUTUBE_COOKIES_PATH")
    if env_path and Path(env_path).exists() and Path(env_path).stat().st_size > 0:
        cookie_file = Path(env_path)

    # 2. Local cookies file in root, config/, or output/
    if not cookie_file:
        project_root = Path(__file__).resolve().parent.parent
        local_candidates = [
            project_root / "cookies.txt",
            DOWNLOAD_DIR.parent / "cookies.txt",
            project_root / "config" / "cookies.txt",
        ]
        for c in local_candidates:
            if c.exists() and c.stat().st_size > 0:
                cookie_file = c
                break

    # 3. Raw cookies content supplied via YOUTUBE_COOKIES env var (from GitHub Secrets or .env)
    if not cookie_file:
        raw = os.environ.get("YOUTUBE_COOKIES", "").strip()
        if raw:
            # Check if base64 encoded
            import base64
            decoded_text = None
            try:
                decoded_bytes = base64.b64decode(raw, validate=True)
                candidate = decoded_bytes.decode("utf-8", errors="ignore")
                if "youtube.com" in candidate or "# Netscape" in candidate:
                    decoded_text = candidate
            except Exception:
                pass

            if not decoded_text and ("youtube.com" in raw or "# Netscape" in raw or "\t" in raw):
                decoded_text = raw

            if decoded_text:
                out_cookie_file = DOWNLOAD_DIR.parent / "cookies.txt"
                out_cookie_file.parent.mkdir(parents=True, exist_ok=True)
                out_cookie_file.write_text(decoded_text, encoding="utf-8")
                cookie_file = out_cookie_file

    if cookie_file and not _COOKIE_LOGGED:
        print(f"[Auth] YouTube cookies active from {cookie_file.name} ({cookie_file.stat().st_size} bytes)")
        _COOKIE_LOGGED = True

    return cookie_file


_POT_LOGGED = False


def _is_pot_provider_active() -> bool:
    global _POT_LOGGED
    # In GitHub Actions, the provider container is always spun up
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return True

    import urllib.request
    for target in ["http://127.0.0.1:4416/ping", "http://localhost:4416/ping"]:
        try:
            req = urllib.request.Request(target, headers={"User-Agent": "yt-dlp"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status in (200, 204):
                    if not _POT_LOGGED:
                        print(f"[Auth] Proof-of-Origin Token Provider online at {target}")
                        _POT_LOGGED = True
                    return True
        except Exception:
            pass

    return False


def _run_proc_clean(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    """Runs a subprocess with hard timeout and process-tree cleanup on hang."""
    popen_kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "errors": "replace",
    }
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout or "", stderr or "")
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=10,
                )
            else:
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout, stderr = "", ""
        timeout_note = f"\n[Timeout] Process aborted after exceeding {timeout}s limit."
        return subprocess.CompletedProcess(cmd, 124, stdout or "", (stderr or "") + timeout_note)


def _has_video_stream(file_path: Path) -> bool:
    """Verifies via ffprobe that file_path exists, is non-empty, and contains a valid video stream."""
    if not file_path.exists() or file_path.stat().st_size < 1024:
        return False
    try:
        res = _run_proc_clean(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type,width,height",
                "-of", "json",
                str(file_path),
            ],
            timeout=15,
        )
        if res.returncode != 0:
            return False
        data = json.loads(res.stdout or "{}")
        return any(
            s.get("codec_type") == "video"
            and int(s.get("width") or 0) > 0
            and int(s.get("height") or 0) > 0
            for s in data.get("streams", [])
        )
    except Exception:
        return False


def _probe_duration(file_path: Path) -> float | None:
    """Returns duration in seconds via ffprobe, or None on error."""
    if not file_path.exists():
        return None
    try:
        res = _run_proc_clean(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(file_path),
            ],
            timeout=15,
        )
        if res.returncode == 0:
            dur = json.loads(res.stdout or "{}").get("format", {}).get("duration")
            return float(dur) if dur is not None else None
    except Exception:
        pass
    return None


def _base_ytdlp_args(
    ignore_cookies: bool = False,
    player_clients: str = "visionos,ios,mweb",
) -> list[str]:
    args = [
        "yt-dlp",
        "--remote-components", "ejs:github",
        "--socket-timeout", "25",
        "--retries", "3",
        "--fragment-retries", "3",
        "--no-check-certificates",
    ]

    # 1. Outbound Proxy Routing (Support dedicated residential/datacenter proxy)
    proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy_url:
        args.extend(["--proxy", proxy_url])

    # 2. Session Cookies with Client Configuration
    cookie_path = get_cookies_path() if not ignore_cookies else None
    if cookie_path:
        args.extend(["--cookies", str(cookie_path)])

    # Put visionos and ios first: they don't require GVS PO tokens, use clean HLS, and bypass cloud bot blocks
    args.extend(["--extractor-args", f"youtube:player_client={player_clients}"])

    # 3. Proof-of-Origin Token Provider (if running)
    if _is_pot_provider_active():
        args.extend(["--extractor-args", "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"])

    # 4. Locate Deno or Node runtime for solving YouTube JS challenges
    deno_path = shutil.which("deno")
    if not deno_path:
        user_deno = Path.home() / ".deno" / "bin" / ("deno.exe" if os.name == "nt" else "deno")
        if user_deno.exists():
            deno_path = str(user_deno)

    if deno_path:
        args.extend(["--js-runtimes", f"deno:{deno_path}"])
    elif shutil.which("node"):
        args.extend(["--js-runtimes", "node"])

    return args


def _run_ytdlp_resilient(
    extra_args: list[str],
    player_clients: str = "visionos,ios,mweb",
    timeout: int = 180,
) -> subprocess.CompletedProcess:
    """Executes yt-dlp with retries for HTTP 429 rate limits and cookie/bot/SABR fallback."""
    cmd1 = _base_ytdlp_args(ignore_cookies=False, player_clients=player_clients) + extra_args
    res = _run_proc_clean(cmd1, timeout=timeout)
    if res.returncode == 0:
        return res

    err_low = ((res.stderr or "") + "\n" + (res.stdout or "")).lower()
    has_cookie = get_cookies_path() is not None

    # Handle HTTP 429 rate limiting with backoff and anonymous fallback
    if "429" in err_low or "too many requests" in err_low:
        print("  [Download] HTTP 429 rate-limit encountered. Waiting 4s and retrying...")
        time.sleep(4.0)
        cmd_429 = _base_ytdlp_args(ignore_cookies=has_cookie, player_clients=player_clients) + extra_args
        res = _run_proc_clean(cmd_429, timeout=timeout)
        if res.returncode == 0:
            return res

        err_low = ((res.stderr or "") + "\n" + (res.stdout or "")).lower()
        if "429" in err_low or "too many requests" in err_low:
            print("  [Download] Still rate-limited (429). Waiting 6s and retrying with alternate client chain...")
            time.sleep(6.0)
            cmd_429_alt = _base_ytdlp_args(ignore_cookies=True, player_clients="android_vr,tv,web") + extra_args
            res_alt = _run_proc_clean(cmd_429_alt, timeout=timeout)
            if res_alt.returncode == 0:
                return res_alt
            return res_alt
        return res

    # If bot challenge, cookie issue, SABR block, or missing format triggered with cookies, retry anonymously
    fallback_markers = (
        "sign in to confirm",
        "bot",
        "cookie",
        "login_info",
        "403",
        "sabr",
        "format is not available",
        "impersonat",
    )
    if has_cookie and any(m in err_low for m in fallback_markers):
        print("  [Download] Primary cookie request encountered challenge/format block. Retrying anonymously...")
        cmd2 = _base_ytdlp_args(ignore_cookies=True, player_clients=player_clients) + extra_args
        res2 = _run_proc_clean(cmd2, timeout=timeout)
        if res2.returncode == 0:
            return res2
        return res2

    return res


def get_video_id(url: str) -> str:
    # Fast regex extraction to avoid network overhead
    match = re.search(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})", url)
    if match:
        return match.group(1)

    result = _run_ytdlp_resilient(["--print", "%(id)s", "--no-download", url], timeout=45)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to get video ID for {url}: {err[-250:]}")
    return result.stdout.strip()


def get_video_info(url: str) -> dict:
    result = _run_ytdlp_resilient(["-J", "--no-download", url], timeout=60)
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to get video info for {url}: {err[-250:]}")
    return json.loads(result.stdout)


def _is_valid_vtt(vtt_path: Path) -> bool:
    """Checks that a VTT file has meaningful timed cue content rather than an empty/header-only stub."""
    try:
        if not vtt_path.exists() or vtt_path.stat().st_size < 250:
            return False
        text = vtt_path.read_text(encoding="utf-8", errors="ignore")
        if "-->" not in text:
            return False
        # Strip timestamps/headers to verify real spoken text is present
        cue_lines = [
            ln.strip() for ln in text.splitlines()
            if ln.strip()
            and not ln.strip().startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
            and "-->" not in ln
        ]
        words = " ".join(cue_lines).split()
        return len(words) >= 15
    except Exception:
        return False


def _pick_best_vtt(video_id: str) -> Path | None:
    """Selects the highest-quality valid English VTT file, preferring en-orig over en and ignoring stubs."""
    valid: list[tuple[int, int, Path]] = []
    for p in DOWNLOAD_DIR.glob(f"{video_id}*.vtt"):
        if not _is_valid_vtt(p):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
            continue
        name = p.name.lower()
        if ".en-orig." in name:
            tier = 0
        elif re.search(r"\.en\.vtt$", name):
            tier = 1
        elif any(f".{code}." in name for code in ("en-us", "en-gb", "en-ca", "en-au")):
            tier = 2
        else:
            tier = 3
        valid.append((tier, -p.stat().st_size, p))

    if not valid:
        return None
    valid.sort(key=lambda item: (item[0], item[1]))
    return valid[0][2]


def download_subtitles(url: str, video_id: str | None = None) -> Path | None:
    """Downloads English subtitles/auto-captions without fetching video bytes.
    Queries single-track selectors sequentially (`en-orig`, then `en`, then regional/wildcard)
    with `--ignore-no-formats-error` to eliminate YouTube HTTP 429 timedtext throttling.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not video_id:
        video_id = get_video_id(url)

    # Clear prior files for this video_id so stubs/stale files are never picked
    for old_vtt in DOWNLOAD_DIR.glob(f"{video_id}*.vtt"):
        try:
            old_vtt.unlink(missing_ok=True)
        except Exception:
            pass

    out_template = str(DOWNLOAD_DIR / f"{video_id}.%(ext)s")
    attempts = [
        ("en-orig", "visionos,ios,mweb"),
        ("en", "visionos,ios,mweb"),
        ("en-US,en-GB,en-CA,en-AU", "visionos,ios,mweb"),
        ("en.*", "android_vr,tv,mweb,web"),
    ]

    last_err_tail = ""
    for idx, (sub_langs, clients) in enumerate(attempts):
        if idx > 0:
            time.sleep(1.5)
        cmd = [
            "--skip-download",
            "--ignore-no-formats-error",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", sub_langs,
            "--sub-format", "vtt",
            "--convert-subs", "vtt",
            "--sleep-subtitles", "2",
            "--force-overwrites",
            "-o", out_template,
            url,
        ]
        res = _run_ytdlp_resilient(cmd, player_clients=clients, timeout=60)

        # Even if a warning or secondary track caused non-zero exit, check if a valid .vtt was written
        picked = _pick_best_vtt(video_id)
        if picked:
            return picked

        if res.returncode != 0:
            err_msg = (res.stderr or res.stdout or "").strip()
            if err_msg:
                last_err_tail = " | ".join(err_msg.splitlines()[-3:])

    if last_err_tail:
        print(f"  [Download] Subtitle extraction note: {last_err_tail[:400]}")
    return None


def _cleanup_section_artifacts(out_name: str, out_path: Path) -> None:
    """Removes partial/stale download files for a target section name before retrying."""
    try:
        out_path.unlink(missing_ok=True)
    except Exception:
        pass
    if DOWNLOAD_DIR.exists():
        for p in DOWNLOAD_DIR.glob(f"{out_name}.*"):
            try:
                if p.is_file():
                    p.unlink(missing_ok=True)
            except Exception:
                pass


def download_clip_section(
    url: str,
    video_id: str,
    start: float,
    end: float,
    out_name: str,
) -> tuple[Path, float, float]:
    """Downloads only the requested time slice of the video using yt-dlp --download-sections.
    Excludes Premium VP9 format 616 (which produces audio-only MP4s on section slices),
    prioritizes fast AVC1 HLS seeking, and strictly validates that output contains video.
    Returns (section_path, relative_start, relative_end).
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOWNLOAD_DIR / f"{out_name}.mp4"
    pad_start = max(0.0, start - 1.5)
    pad_end = end + 1.5
    section_spec = f"*{pad_start:.2f}-{pad_end:.2f}"

    primary_fmt = (
        "bv*[height<=1080][vcodec^=avc1][protocol*=m3u8]+ba[protocol*=m3u8]/"
        "bv*[height<=1080][format_id!=616][protocol*=m3u8][vcodec!=none]+ba[protocol*=m3u8]/"
        "bv*[height<=1080][vcodec^=avc1][vcodec!=none]+ba/"
        "bv*[height<=1080][format_id!=616][vcodec!=none]+ba/"
        "b[height<=1080][vcodec!=none]/18"
    )
    fallback_fmt = (
        "bv*[height<=1080][format_id!=616][protocol*=m3u8][vcodec!=none]+ba[protocol*=m3u8]/"
        "bv*[height<=1080][vcodec^=avc1][vcodec!=none]+ba/"
        "bv*[height<=1080][format_id!=616][vcodec!=none]+ba/"
        "18/b[height<=720][vcodec!=none]"
    )

    attempts = [
        ("avc1_hls_keyframes", primary_fmt, True, "visionos,ios,mweb", 90),
        ("avc1_hls_direct", primary_fmt, False, "visionos,ios,mweb", 90),
        ("fallback_alt_clients", fallback_fmt, False, "android_vr,tv,mweb,web", 120),
    ]

    last_error = "Unknown yt-dlp section download failure"
    for idx, (label, fmt, use_keyframes, clients, step_timeout) in enumerate(attempts):
        _cleanup_section_artifacts(out_name, out_path)

        cmd = ["-f", fmt, "--download-sections", section_spec]
        if use_keyframes:
            cmd.append("--force-keyframes-at-cuts")
        cmd.extend([
            "--merge-output-format", "mp4",
            "--force-overwrites",
            "-o", str(out_path),
            url,
        ])

        res = _run_ytdlp_resilient(cmd, player_clients=clients, timeout=step_timeout)
        if res.returncode == 0 and _has_video_stream(out_path):
            relative_start = start - pad_start
            relative_end = relative_start + (end - start)
            return out_path, relative_start, relative_end

        if res.returncode == 0 and out_path.exists():
            size_kb = out_path.stat().st_size // 1024
            last_error = f"Attempt '{label}' wrote file ({size_kb} KB) without a valid video stream"
            print(f"  [Download] {last_error}. Retrying with next strategy...")
        else:
            err_msg = (res.stderr or res.stdout or "").strip()
            tail = "\n".join(err_msg.splitlines()[-4:]) if err_msg else f"exit code {res.returncode}"
            last_error = tail
            if idx < len(attempts) - 1:
                print(f"  [Download] Section strategy '{label}' failed ({tail.splitlines()[-1] if tail else res.returncode}), retrying...")

    _cleanup_section_artifacts(out_name, out_path)
    raise RuntimeError(f"yt-dlp clip section download failed:\n{last_error}")


def cleanup_intermediate_files(prefix: str) -> None:
    """Removes intermediate slice files and temporary artifacts for a video."""
    if not DOWNLOAD_DIR.exists():
        return
    for f in DOWNLOAD_DIR.glob(f"{prefix}*"):
        try:
            if f.is_file():
                f.unlink(missing_ok=True)
        except Exception:
            pass


def download_video(
    url: str,
    video_id: str | None = None,
    title: str | None = None,
    fetch_subs: bool = True,
) -> dict:
    """Downloads full video (mp4) + optional subtitles to output/downloads/<id>.*
    Returns dict with paths and metadata: {video_path, subtitle_path (or None), video_id, title, duration}
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not video_id:
        video_id = get_video_id(url)
    video_path = DOWNLOAD_DIR / f"{video_id}.mp4"
    _cleanup_section_artifacts(video_id, video_path)
    out_template = str(DOWNLOAD_DIR / f"{video_id}.%(ext)s")

    full_fmt = (
        "bv*[height<=1080][vcodec^=avc1][vcodec!=none]+ba[ext=m4a]/"
        "bv*[height<=1080][format_id!=616][vcodec!=none]+ba/"
        "b[height<=1080][vcodec!=none]/18"
    )

    cmd = [
        "-f", full_fmt,
        "--merge-output-format", "mp4",
        "--force-overwrites",
        "-o", out_template,
        url,
    ]
    res = _run_ytdlp_resilient(cmd, timeout=240)
    if res.returncode != 0 or not _has_video_stream(video_path):
        err_msg = (res.stderr or res.stdout or "").strip()
        if res.returncode == 0:
            err_msg = (err_msg + "\nDownloaded full video MP4 missing valid video stream.").strip()
        print(f"  [Download Error Output]:\n{err_msg}")
        _cleanup_section_artifacts(video_id, video_path)
        last_error = "\n".join(err_msg.splitlines()[-6:]) if err_msg else "Unknown yt-dlp error"
        raise RuntimeError(f"yt-dlp video download failed:\n{last_error}")

    subtitle_path = _pick_best_vtt(video_id)
    if not subtitle_path and fetch_subs:
        try:
            subtitle_path = download_subtitles(url, video_id=video_id)
        except Exception:
            subtitle_path = None

    actual_duration = _probe_duration(video_path)

    if not title:
        try:
            info = get_video_info(url)
            title = info.get("title", video_id)
        except Exception:
            title = video_id

    return {
        "video_id": video_id,
        "title": title,
        "video_path": video_path,
        "subtitle_path": subtitle_path,
        "duration": actual_duration,
    }
