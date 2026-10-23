"""Multi-Platform Packaging & Export Module.

Packages rendered YouTube Shorts into standardized bundles for multi-platform distribution
(TikTok, Instagram Reels, and YouTube Shorts), generating:
  - Video file (1080x1920 MP4)
  - Extracted 1.5s high-impact cover thumbnail (JPEG)
  - Platform-tailored captions (TikTok < 2200 chars, Instagram structured captions with CTAs)
  - Machine-readable metadata.json for third-party schedulers (Buffer, Metricool, Hootsuite)
"""
import json
import shutil
import subprocess
from pathlib import Path

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "output" / "exports"


def _extract_cover_frame(video_path: Path, output_cover_path: Path, timestamp_sec: float = 1.5) -> bool:
    """Extracts a high-impact still frame from the video using FFmpeg for the cover image."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{timestamp_sec:.3f}",
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(output_cover_path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        return result.returncode == 0 and output_cover_path.exists() and output_cover_path.stat().st_size > 0
    except Exception as e:
        print(f"  [Export] Warning: Could not extract cover thumbnail: {e}")
        return False


def _format_tiktok_caption(
    hook: str,
    takeaway: str | None,
    handle: str,
    hashtags: list[str],
) -> str:
    """Formats a punchy, algorithm-friendly caption for TikTok (< 2200 chars)."""
    clean_tags = [f"#{t.lstrip('#')}" for t in hashtags[:6]]
    if "#fyp" not in clean_tags:
        clean_tags.insert(0, "#fyp")
    if "#viral" not in clean_tags:
        clean_tags.append("#viral")

    lines = [
        hook.strip(),
        "",
    ]
    if takeaway:
        lines.append(f"💡 {takeaway.strip()}")
        lines.append("")
    lines.extend([
        f"Follow {handle} for more daily gems! 🔔",
        "",
        " ".join(clean_tags),
    ])
    return "\n".join(lines).strip()[:2150]


def _format_instagram_caption(
    hook: str,
    takeaway: str | None,
    channel_name: str,
    handle: str,
    source_creator: str | None,
    hashtags: list[str],
) -> str:
    """Formats a structured, high-engagement Instagram Reels caption with hooks, insight, and CTA."""
    clean_tags = [f"#{t.lstrip('#')}" for t in hashtags[:15]]
    for default_tag in ["#reels", "#explorepage", "#viralreels"]:
        if default_tag not in clean_tags and len(clean_tags) < 20:
            clean_tags.append(default_tag)

    lines = [
        f"🎯 {hook.strip()}",
        "",
    ]
    if takeaway:
        lines.extend([
            f"💡 Key Takeaway: {takeaway.strip()}",
            "",
        ])
    if source_creator:
        lines.extend([
            f"🎙️ Via / Creator: {source_creator}",
            "",
        ])
    lines.extend([
        "📌 Save this reel so you don't forget it!",
        f"👉 Follow @{handle.lstrip('@')} for daily {channel_name.lower()} updates.",
        "",
        ".".join(["\n"] * 3),  # Subtle spacing before tags
        " ".join(clean_tags),
    ])
    return "\n".join(lines).strip()[:2200]


def export_multiplatform_bundle(
    captioned_video_path: Path,
    channel_id: str,
    video_id: str,
    clip_index: int,
    pick: dict,
    cfg: dict,
    duration_sec: float,
    source_url: str | None = None,
    source_channel: str | None = None,
) -> Path:
    """Generates a complete multi-platform publishing bundle for TikTok, Instagram Reels, and YouTube Shorts.

    Returns:
        Path: Path to the generated bundle directory.
    """
    bundle_dir = EXPORTS_DIR / channel_id / f"{video_id}_clip{clip_index + 1}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy video file to bundle
    bundle_video = bundle_dir / "video.mp4"
    if captioned_video_path.exists():
        shutil.copy2(captioned_video_path, bundle_video)

    # 2. Extract cover image thumbnail (at 1.5s)
    cover_path = bundle_dir / "cover.jpg"
    _extract_cover_frame(captioned_video_path, cover_path, timestamp_sec=min(1.5, duration_sec / 2.0))

    # 3. Read metadata parameters
    branding = cfg.get("branding", {})
    meme_cfg = cfg.get("meme_template", {})
    ch_name = branding.get("channel_name", channel_id.replace("_", " ").title())
    handle = meme_cfg.get("handle") or branding.get("handle", f"@{channel_id}")

    disc_cfg = cfg.get("discovery", {})
    raw_tags = disc_cfg.get("scrape_hashtags", [])
    clean_tags = [t.lstrip("#").strip() for t in raw_tags if t.strip()]

    hook_text = pick.get("burner_text") or pick.get("hook") or pick.get("title", "Insight")
    takeaway_text = pick.get("takeaway")

    # 4. Generate platform-specific caption text files
    tiktok_caption = _format_tiktok_caption(
        hook=hook_text,
        takeaway=takeaway_text,
        handle=handle,
        hashtags=clean_tags,
    )
    (bundle_dir / "tiktok_caption.txt").write_text(tiktok_caption, encoding="utf-8")

    ig_caption = _format_instagram_caption(
        hook=hook_text,
        takeaway=takeaway_text,
        channel_name=ch_name,
        handle=handle,
        source_creator=source_channel,
        hashtags=clean_tags,
    )
    (bundle_dir / "instagram_caption.txt").write_text(ig_caption, encoding="utf-8")

    # 5. Generate comprehensive metadata.json
    metadata = {
        "channel_id": channel_id,
        "channel_name": ch_name,
        "handle": handle,
        "source_video_id": video_id,
        "source_url": source_url,
        "source_creator": source_channel,
        "clip_index": clip_index + 1,
        "duration_seconds": round(duration_sec, 2),
        "hook_title": hook_text,
        "takeaway": takeaway_text,
        "files": {
            "video": str(bundle_video.name),
            "cover": str(cover_path.name) if cover_path.exists() else None,
            "tiktok_caption": "tiktok_caption.txt",
            "instagram_caption": "instagram_caption.txt",
        },
        "platforms": {
            "youtube_shorts": {
                "title": f"{hook_text} #shorts"[:100],
                "tags": clean_tags + ["shorts", "viral"],
            },
            "tiktok": {
                "caption": tiktok_caption,
            },
            "instagram_reels": {
                "caption": ig_caption,
            },
        },
    }
    (bundle_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"     [Export] Multi-platform bundle created at: {bundle_dir}")
    return bundle_dir
