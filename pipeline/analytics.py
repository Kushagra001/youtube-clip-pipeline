"""YouTube Shorts Retention Analytics & Continuous Feedback Engine.

Tracks real-time view counts, likes, and engagement metrics across uploaded Shorts
using zero-quota yt-dlp metadata extraction (and optional YouTube Data API fallback).
Calculates creator performance indices and automatically tunes discovery weights
to scale high-retention formats and deprioritize underperforming topics.
"""
import os
import sys
import time
from statistics import median
from pathlib import Path
import yt_dlp

from pipeline import state as state_mod

# Ensure UTF-8 output across Windows and Linux terminals
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class _SilentLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _get_stats_extractor() -> yt_dlp.YoutubeDL:
    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "logger": _SilentLogger(),
        "socket_timeout": 15,
        "retries": 2,
    }
    proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTPS_PROXY")
    if proxy_url:
        opts["proxy"] = proxy_url
    return yt_dlp.YoutubeDL(opts)


def fetch_short_stats(video_id: str) -> dict:
    """Fetches public performance statistics for a YouTube Short with 0 quota consumption."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with _get_stats_extractor() as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {
                    "status": "pending_or_private",
                    "views": 0,
                    "likes": 0,
                    "comments": 0,
                    "synced": False,
                }
            views = int(info.get("view_count") or 0)
            likes = int(info.get("like_count") or 0)
            comments = int(info.get("comment_count") or 0)
            return {
                "status": "public",
                "views": views,
                "likes": likes,
                "comments": comments,
                "title": info.get("title", ""),
                "synced": True,
            }
    except Exception as e:
        return {
            "status": "pending_or_private",
            "views": 0,
            "likes": 0,
            "comments": 0,
            "synced": False,
            "note": str(e)[:120],
        }


def sync_channel_analytics(channel_id: str, state: dict | None = None, force: bool = False) -> dict:
    """Synchronizes performance metrics for all uploaded Shorts of a channel and updates feedback weights."""
    if state is None:
        state = state_mod.load_state(channel_id)

    uploaded = state.get("uploaded_shorts", [])
    if not uploaded:
        return {
            "channel_id": channel_id,
            "total_shorts": 0,
            "total_views": 0,
            "creator_weights": {},
            "public_shorts": 0,
        }

    now = time.time()
    updated_count = 0
    views_list = []
    creator_view_map: dict[str, list[int]] = {}

    for item in uploaded:
        v_id = item.get("video_id")
        if not v_id:
            continue

        creator = item.get("creator") or "Unknown"
        stats = item.setdefault("stats", {})
        last_synced = stats.get("last_synced", 0)

        # Only sync if forced or if > 45 minutes since last check
        if force or (now - last_synced > 2700):
            res = fetch_short_stats(v_id)
            if res.get("synced"):
                stats["views"] = res["views"]
                stats["likes"] = res["likes"]
                stats["comments"] = res["comments"]
                stats["status"] = "public"
            else:
                stats["status"] = res.get("status", "pending_or_private")
            stats["last_synced"] = now
            updated_count += 1

        v_count = stats.get("views", 0)
        if stats.get("status") == "public" and v_count > 0:
            views_list.append(v_count)
            creator_view_map.setdefault(creator, []).append(v_count)

    # Calculate channel baseline and creator affinity multipliers
    med_views = median(views_list) if views_list else 100.0
    creator_weights: dict[str, float] = {}

    for c_handle, c_views in creator_view_map.items():
        if not c_views:
            continue
        c_avg = sum(c_views) / float(len(c_views))
        ratio = c_avg / max(med_views, 1.0)
        if ratio >= 2.2:
            weight = 1.8  # Viral superstar (boosted 80%)
        elif ratio >= 1.25:
            weight = 1.35 # Strong performer (boosted 35%)
        elif ratio <= 0.4 and len(c_views) >= 2:
            weight = 0.65 # Underperformer (penalized 35%)
        else:
            weight = 1.0
        creator_weights[c_handle] = weight

    total_v = sum(views_list)
    summary = {
        "channel_id": channel_id,
        "last_sync": now,
        "total_shorts": len(uploaded),
        "public_shorts": len(views_list),
        "total_views": total_v,
        "median_views": med_views,
        "creator_weights": creator_weights,
    }

    state["analytics_summary"] = summary
    state_mod.save_state(state, channel_id=channel_id)
    return summary


def get_creator_tuning_multiplier(creator_handle: str, state: dict) -> tuple[float, str]:
    """Returns the discovery virality multiplier for a creator based on historical channel analytics.

    Returns:
        tuple[float, str]: (multiplier, reason_label)
    """
    summary = state.get("analytics_summary") or {}
    weights = summary.get("creator_weights") or {}
    c_clean = creator_handle.strip().lower()

    for handle, mult in weights.items():
        h_clean = handle.strip().lower()
        if h_clean == c_clean or h_clean.lstrip("@") == c_clean.lstrip("@"):
            if mult > 1.3:
                return mult, "High-Retention Creator (+%d%%)" % int((mult - 1.0) * 100)
            elif mult < 0.8:
                return mult, "Low-Retention Creator (-%d%%)" % int((1.0 - mult) * 100)
            return mult, "Normal Performance"

    return 1.0, "Fresh Creator"


def render_analytics_dashboard(channel_id: str, state: dict | None = None) -> str:
    """Generates an ASCII analytics dashboard report for the channel."""
    if state is None:
        state = state_mod.load_state(channel_id)

    summary = state.get("analytics_summary") or sync_channel_analytics(channel_id, state)
    uploaded = state.get("uploaded_shorts", [])

    lines = [
        "",
        "=" * 76,
        f"  📊 YOUTUBE SHORTS ANALYTICS DASHBOARD: {channel_id.upper()}",
        "=" * 76,
        f"  Total Uploaded Shorts: {len(uploaded)} | Public Shorts: {summary.get('public_shorts', 0)}",
        f"  Total Views Tracked:   {summary.get('total_views', 0):,} views",
        f"  Median Views / Short:  {summary.get('median_views', 0):.0f} views",
        "-" * 76,
        "  [Algorithmic Self-Tuning Weights for Discovery]",
    ]

    weights = summary.get("creator_weights", {})
    if weights:
        for c, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            status = "🟢 BOOSTED" if w > 1.0 else ("🔴 PENALIZED" if w < 1.0 else "⚪ NEUTRAL")
            lines.append(f"    * {c:<24} Weight: {w:.2f}x ({status})")
    else:
        lines.append("    (No creator affinity weights established yet; accumulates after public views).")

    lines.extend([
        "-" * 76,
        f"  {'Video ID':<13} {'Status':<10} {'Views':<10} {'Likes':<8} {'Creator':<20} Title",
        "-" * 76,
    ])

    for it in uploaded[-15:]:
        v_id = it.get("video_id", "N/A")
        stats = it.get("stats", {})
        status = stats.get("status", "pending")
        v_views = f"{stats.get('views', 0):,}"
        v_likes = f"{stats.get('likes', 0):,}"
        creator = (it.get("creator") or "Unknown")[:18]
        title = (it.get("title") or "")[:28]
        lines.append(f"  {v_id:<13} {status:<10} {v_views:<10} {v_likes:<8} {creator:<20} {title}...")

    lines.append("=" * 76)
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Clipping Pipeline Analytics Dashboard")
    parser.add_argument("--channel", type=str, default="", help="Channel ID (e.g. acc_08_ai_tools or omit for default)")
    parser.add_argument("--force", action="store_true", help="Force refresh metrics immediately from YouTube")
    args = parser.parse_args()

    cid = args.channel or "acc_08_ai_tools"
    st = state_mod.load_state(cid)
    sync_channel_analytics(cid, st, force=args.force)
    print(render_analytics_dashboard(cid, st))
