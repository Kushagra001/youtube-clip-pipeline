import os
import re
import shutil
import subprocess
import json
from pathlib import Path

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "output" / "downloads"


def get_cookies_path() -> Path | None:
    """Finds or creates a valid cookies file from environment secrets or workspace files."""
    # 1. Direct explicit environment path
    env_path = os.environ.get("YOUTUBE_COOKIES_PATH")
    if env_path and Path(env_path).exists() and Path(env_path).stat().st_size > 0:
        return Path(env_path)

    # 2. Local cookies file in root, config/, or output/
    project_root = Path(__file__).resolve().parent.parent
    local_candidates = [
        project_root / "cookies.txt",
        project_root / "config" / "cookies.txt",
        DOWNLOAD_DIR.parent / "cookies.txt",
    ]
    for c in local_candidates:
        if c.exists() and c.stat().st_size > 0:
            return c

    # 3. Raw cookies content supplied via YOUTUBE_COOKIES env var (from GitHub Secrets or .env)
    raw = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if raw and ("youtube.com" in raw or "# Netscape" in raw or "\t" in raw):
        out_cookie_file = DOWNLOAD_DIR.parent / "cookies.txt"
        out_cookie_file.parent.mkdir(parents=True, exist_ok=True)
        out_cookie_file.write_text(raw, encoding="utf-8")
        return out_cookie_file

    return None


def _base_ytdlp_args() -> list[str]:
    args = [
        "yt-dlp",
        "--remote-components", "ejs:github",
    ]
    cookie_path = get_cookies_path()
    if cookie_path:
        args.extend(["--cookies", str(cookie_path)])
        args.extend(["--extractor-args", "youtube:player_client=web,default"])
    else:
        args.extend(["--extractor-args", "youtube:player_client=visionos,android"])

    # Locate Deno or Node runtime for solving YouTube JS challenges
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


def get_video_id(url: str) -> str:
    result = subprocess.run(
        _base_ytdlp_args() + ["--print", "%(id)s", "--no-download", url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Fallback to regex extraction if yt-dlp metadata query fails
        match = re.search(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})", url)
        if match:
            return match.group(1)
        err = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to get video ID for {url}: {err[:250]}")
    return result.stdout.strip()


def get_video_info(url: str) -> dict:
    result = subprocess.run(
        _base_ytdlp_args() + ["-J", "--no-download", url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def download_subtitles(url: str, video_id: str | None = None) -> Path | None:
    """Downloads ONLY the available English subtitles/auto-captions without fetching the video file.
    Fast and uses zero video bandwidth (<50KB).
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not video_id:
        video_id = get_video_id(url)
    out_template = str(DOWNLOAD_DIR / f"{video_id}.%(ext)s")

    cmd = _base_ytdlp_args() + [
        "--skip-download",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "en.*,hi.*,en-IN,hi-Latn,en-US,en-GB",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "-o", out_template,
        url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
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

    cmd = _base_ytdlp_args() + [
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/18/best",
        "--download-sections", section_spec,
        "--force-keyframes-at-cuts",
        "--merge-output-format", "mp4",
        "-o", str(out_path),
        url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
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

    cmd = _base_ytdlp_args() + [
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/18/best",
        "--merge-output-format", "mp4",
        "--write-subs", "--write-auto-subs",
        "--sub-langs", "en.*,hi.*,en-IN,hi-Latn,en-US,en-GB",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "-o", out_template,
        url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        err_msg = res.stderr.strip() or res.stdout.strip()
        last_error = "\n".join(err_msg.splitlines()[-4:]) if err_msg else "Unknown yt-dlp error"
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

