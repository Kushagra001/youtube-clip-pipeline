import os
import re
import shutil
import subprocess
import json
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
        except Exception as e:
            pass

    return False


def _base_ytdlp_args(ignore_cookies: bool = False) -> list[str]:
    args = [
        "yt-dlp",
        "--remote-components", "ejs:github",
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
        args.extend(["--extractor-args", "youtube:player_client=visionos,ios,mweb"])
    else:
        args.extend(["--extractor-args", "youtube:player_client=visionos,ios,mweb"])

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


def _run_ytdlp_resilient(extra_args: list[str]) -> subprocess.CompletedProcess:
    """Executes yt-dlp with primary configuration, and falls back gracefully if cookie/auth/bot issue occurs."""
    cmd1 = _base_ytdlp_args(ignore_cookies=False) + extra_args
    res = subprocess.run(cmd1, capture_output=True, text=True)
    if res.returncode == 0:
        return res

    err = (res.stderr or "") + " " + (res.stdout or "")
    has_cookie = get_cookies_path() is not None
    # If bot challenge or cookie issue triggered, retry once without session cookies
    if has_cookie and any(x in err.lower() for x in ["sign in to confirm", "bot", "cookie", "login_info"]):
        print("  [Download] Primary cookie request encountered bot challenge. Retrying anonymously with clean client chain...")
        cmd2 = _base_ytdlp_args(ignore_cookies=True) + extra_args
        res2 = subprocess.run(cmd2, capture_output=True, text=True)
        if res2.returncode == 0:
            return res2
        return res2

    return res


def get_video_id(url: str) -> str:
    # Fast regex extraction to avoid network overhead
    match = re.search(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})", url)
    if match:
        return match.group(1)

    result = _run_ytdlp_resilient(["--print", "%(id)s", "--no-download", url])
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to get video ID for {url}: {err[:250]}")
    return result.stdout.strip()


def get_video_info(url: str) -> dict:
    result = _run_ytdlp_resilient(["-J", "--no-download", url])
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to get video info for {url}: {err[:250]}")
    return json.loads(result.stdout)


def download_subtitles(url: str, video_id: str | None = None) -> Path | None:
    """Downloads ONLY the available English subtitles/auto-captions without fetching the video file.
    Fast and uses zero video bandwidth (<50KB).
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not video_id:
        video_id = get_video_id(url)
    out_template = str(DOWNLOAD_DIR / f"{video_id}.%(ext)s")

    cmd = [
        "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "en.*,hi.*,en-IN,hi-Latn,en-US,en-GB",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "-o", out_template,
        url,
    ]
    res = _run_ytdlp_resilient(cmd)
    if res.returncode != 0:
        err_msg = res.stderr.strip() or res.stdout.strip()
        print(f"  [Download] Subtitle extraction note: {err_msg[:250]}")

    candidates = list(DOWNLOAD_DIR.glob(f"{video_id}*.vtt"))
    return candidates[0] if candidates else None


def download_clip_section(
    url: str,
    video_id: str,
    start: float,
    end: float,
    out_name: str,
) -> tuple[Path, float, float]:
    """Downloads only the requested time slice of the video using yt-dlp --download-sections.
    Pads by 1.5 seconds on both sides for keyframe safety.
    Returns (section_path, relative_start, relative_end).
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOWNLOAD_DIR / f"{out_name}.mp4"
    pad_start = max(0.0, start - 1.5)
    pad_end = end + 1.5
    section_spec = f"*{pad_start:.2f}-{pad_end:.2f}"

    cmd = [
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/18/best",
        "--download-sections", section_spec,
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
        url,
    ]
    res = _run_ytdlp_resilient(cmd)
    if res.returncode != 0:
        err_msg = res.stderr.strip() or res.stdout.strip()
        last_error = "\n".join(err_msg.splitlines()[-4:]) if err_msg else "Unknown yt-dlp error"
        raise RuntimeError(f"yt-dlp clip section download failed:\n{last_error}")

    relative_start = start - pad_start
    relative_end = relative_start + (end - start)
    return out_path, relative_start, relative_end


def download_video(url: str, video_id: str | None = None, title: str | None = None) -> dict:
    """Downloads full video (mp4) + subtitles (if present) to output/downloads/<id>.*
    Returns dict with paths: {video_path, subtitle_path (or None), video_id, title}
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not video_id:
        video_id = get_video_id(url)
    out_template = str(DOWNLOAD_DIR / f"{video_id}.%(ext)s")

    cmd = [
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/18/best",
        "--merge-output-format", "mp4",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "en.*,hi.*,en-IN,hi-Latn,en-US,en-GB",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "-o", out_template,
        url,
    ]
    res = _run_ytdlp_resilient(cmd)
    if res.returncode != 0:
        err_msg = res.stderr.strip() or res.stdout.strip()
        print(f"  [Download Error Output]:\n{err_msg}")
        last_error = "\n".join(err_msg.splitlines()[-6:]) if err_msg else "Unknown yt-dlp error"
        raise RuntimeError(f"yt-dlp video download failed:\n{last_error}")

    video_path = DOWNLOAD_DIR / f"{video_id}.mp4"
    subtitle_candidates = list(DOWNLOAD_DIR.glob(f"{video_id}*.vtt"))
    subtitle_path = subtitle_candidates[0] if subtitle_candidates else None

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
    }

