"""Autonomous discovery of viral creators and high-performing long-form videos.

Works 100% on free tiers and requires no paid APIs:
- Uses yt-dlp's search and metadata extraction (no YouTube API quota consumed).
- Optionally leverages Groq free-tier LLM (Llama 3.3) for niche expansion if GROQ_API_KEY is present.
"""
import os
import re
import json
from typing import Optional
import yt_dlp

from pipeline import state as state_mod


def _get_ydl(search_depth: int = 25) -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL({
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "playlistend": search_depth,
    })


def search_youtube_videos(query: str, max_results: int = 20) -> list[dict]:
    """Searches YouTube using yt-dlp and returns flat metadata for candidate videos."""
    search_query = f"ytsearch{max_results}:{query}"
    videos = []
    try:
        with _get_ydl(search_depth=max_results) as ydl:
            res = ydl.extract_info(search_query, download=False)
            entries = res.get("entries", []) if res else []
            for entry in entries:
                if not entry:
                    continue
                v_id = entry.get("id")
                if not v_id:
                    continue
                videos.append({
                    "video_id": v_id,
                    "url": f"https://www.youtube.com/watch?v={v_id}",
                    "title": entry.get("title", ""),
                    "channel": entry.get("uploader") or entry.get("channel") or "Unknown",
                    "duration": entry.get("duration"),  # seconds (float/int or None)
                    "view_count": entry.get("view_count") or 0,
                    "query_source": query,
                })
    except Exception as e:
        print(f"  [Discovery] Warning: Search failed for query '{query}': {e}")
    return videos


def get_creator_viral_videos(creator: str, max_results: int = 20) -> list[dict]:
    """Finds top videos from a creator handle (e.g. '@hubermanlab') or creator name."""
    clean_handle = creator.strip()
    # Search query targeting long-form discussions/episodes for this creator
    query = f"{clean_handle} podcast interview full episode"
    return search_youtube_videos(query, max_results=max_results)


def expand_niches_with_groq(niches: list[str]) -> list[str]:
    """Optionally uses free-tier Groq Llama 3.3 to brainstorm specific viral search queries

    and top creators for the requested niches.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return []

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        prompt = (
            f"Given these content niches: {json.dumps(niches)}\n"
            "Generate 5 high-converting YouTube search queries that will find viral long-form podcasts, "
            "interviews, or video essays with high viewership.\n"
            "Also list 3 top viral YouTube channel names/handles in these niches.\n"
            "Respond ONLY with a JSON object: {\"queries\": [\"...\"], \"creators\": [\"...\"]}"
        )
        models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        data = None
        for model_name in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a viral YouTube content strategist. Output only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5,
                    max_tokens=600,
                )
                raw = response.choices[0].message.content or ""
                raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
                data = json.loads(raw)
                if data:
                    break
            except Exception:
                continue

        if not data:
            return []

        expanded = []
        if isinstance(data.get("queries"), list):
            expanded.extend(data["queries"])
        if isinstance(data.get("creators"), list):
            for c in data["creators"]:
                expanded.append(f"{c} full episode")
        return expanded
    except Exception as e:
        print(f"  [Discovery] Groq niche expansion skipped: {e}")
        return []


def filter_and_rank_candidates(
    candidates: list[dict],
    state: dict,
    min_views: int = 50_000,
    min_duration_sec: int = 600,
    max_duration_sec: int = 7200,
    blacklist_terms: list[str] | None = None,
) -> list[dict]:
    """Filters candidate videos for virality criteria, duration boundaries,
    blacklist safety (anti-DMCA protection), and idempotency.
    """
    valid = []
    seen_ids = set()

    for cand in candidates:
        v_id = cand["video_id"]
        if v_id in seen_ids:
            continue
        if state_mod.is_processed(state, v_id):
            continue

        # Litigious content safety filter (avoids automated DMCA strikes from TV/studios/sports)
        if blacklist_terms:
            t_lower = cand.get("title", "").lower()
            c_lower = str(cand.get("channel", "")).lower()
            if any(term in t_lower or term in c_lower for term in blacklist_terms):
                continue

        duration = cand.get("duration")
        # Ensure duration fits long-form constraints (default 10m to 120m)
        if duration is not None:
            if duration < min_duration_sec or duration > max_duration_sec:
                continue

        view_count = cand.get("view_count", 0)
        if min_views > 0 and view_count < min_views:
            continue

        seen_ids.add(v_id)
        valid.append(cand)

    # Sort descending by view count (most viral first)
    valid.sort(key=lambda x: x.get("view_count", 0), reverse=True)
    return valid


def discover_and_select_videos(cfg: dict, state: dict) -> list[dict]:
    """Discovers viral creators and long-form videos based on config settings.

    Returns a prioritized list of video candidates ready for clipping.
    """
    disc_cfg = cfg.get("discovery", {})
    if not disc_cfg.get("enabled", False):
        return []

    niches = disc_cfg.get("niches", [])
    creators = disc_cfg.get("creators", [])
    blacklist_terms = [b.lower().strip() for b in disc_cfg.get("blacklist_terms", []) if b]
    min_views = disc_cfg.get("min_views", 100_000)
    min_dur_min = disc_cfg.get("min_duration_minutes", 10)
    max_dur_min = disc_cfg.get("max_duration_minutes", 120)
    max_per_run = disc_cfg.get("max_videos_per_run", 2)
    max_per_creator = disc_cfg.get("max_videos_per_creator", 1)

    min_dur_sec = int(min_dur_min * 60)
    max_dur_sec = int(max_dur_min * 60)

    all_candidates: list[dict] = []

    print("\n=== Running Viral Creator & Content Discovery ===")

    # 1. Search specified creators
    for creator in creators:
        print(f"  [Discovery] Checking creator: {creator}")
        c_videos = get_creator_viral_videos(creator, max_results=15)
        all_candidates.extend(c_videos)

    # 2. Search specified niches
    for niche in niches:
        print(f"  [Discovery] Exploring niche: '{niche}'")
        n_videos = search_youtube_videos(f"{niche} viral podcast full interview", max_results=20)
        all_candidates.extend(n_videos)

    # 3. Optional Groq expansion if key is available
    groq_expanded = expand_niches_with_groq(niches)
    for q in groq_expanded[:3]:  # sample top 3 generated queries
        print(f"  [Discovery] Exploring AI-suggested query: '{q}'")
        g_videos = search_youtube_videos(q, max_results=15)
        all_candidates.extend(g_videos)

    print(f"  [Discovery] Gathered {len(all_candidates)} raw candidate entries across sources.")

    # 4. Filter and rank
    ranked = filter_and_rank_candidates(
        all_candidates,
        state=state,
        min_views=min_views,
        min_duration_sec=min_dur_sec,
        max_duration_sec=max_dur_sec,
        blacklist_terms=blacklist_terms,
    )

    print(f"  [Discovery] {len(ranked)} candidates passed virality filters (views >= {min_views:,}, duration: {min_dur_min}m-{max_dur_min}m).")

    # 5. Cap per creator and select top videos
    selected = []
    creator_counts: dict[str, int] = {}

    for cand in ranked:
        channel = cand.get("channel", "Unknown")
        count = creator_counts.get(channel, 0)
        if count >= max_per_creator:
            continue

        selected.append(cand)
        creator_counts[channel] = count + 1

        if len(selected) >= max_per_run:
            break

    for i, s in enumerate(selected):
        views_str = f"{s['view_count']:,}" if s.get("view_count") else "N/A"
        dur_str = f"{int(s['duration'] // 60)}m" if s.get("duration") else "N/A"
        safe_title = s.get("title", "")[:55].encode("ascii", errors="replace").decode("ascii")
        safe_channel = str(s.get("channel", "Unknown")).encode("ascii", errors="replace").decode("ascii")
        print(f"  * Selected #{i+1}: '{safe_title}...' | Channel: {safe_channel} | Views: {views_str} | Dur: {dur_str}")

    return selected
