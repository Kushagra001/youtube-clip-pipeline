import shutil
import subprocess
import json
from pathlib import Path

DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "output" / "downloads"


def _base_ytdlp_args() -> list[str]:
    args = ["yt-dlp", "--extractor-args", "youtube:player_client=android,web"]
    if shutil.which("node"):
        args.extend(["--js-runtimes", "node"])
    return args


def get_video_id(url: str) -> str:
    result = subprocess.run(
        _base_ytdlp_args() + ["--print", "%(id)s", "--no-download", url],
        capture_output=True, text=True, check=True,
    )
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

    try:
        cmd = _base_ytdlp_args() + [
            "--skip-download",
            "--write-subs", "--write-auto-subs",
            "--sub-langs", "en.*",
            "--sub-format", "vtt",
            "--convert-subs", "vtt",
            "-o", out_template,
            url,
        ]
        subprocess.run(
            cmd,
            capture_output=True,
            check=True,
        )
    except Exception as e:
        print(f"  [Download] Subtitle extraction note: {e}")

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
    subprocess.run(cmd, check=True, capture_output=True)

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
        "--sub-langs", "en.*",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "-o", out_template,
        url,
    ]
    subprocess.run(cmd, check=True)

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
