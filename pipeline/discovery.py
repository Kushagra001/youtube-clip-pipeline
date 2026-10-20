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


def get_creator_viral_videos(creator: str, max_results: int = 15, niche_hint: str = "") -> list[dict]:
    """Finds top videos from a creator handle or channel name, optionally filtered by niche topic."""
    clean_handle = creator.strip()
    query = f"{clean_handle} {niche_hint}".strip() if niche_hint else clean_handle
    return search_youtube_videos(query, max_results=max_results)


def extract_niche_keywords(disc_cfg: dict) -> set[str]:
    """Extracts distinctive content keywords from channel niche descriptions."""
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "how", "why", "what",
        "to", "in", "on", "of", "a", "an", "full", "episode", "podcast", "video",
        "best", "top", "viral", "interview", "new", "things", "facts", "lessons",
        "story", "speech", "talk", "guide", "routine"
    }
    keywords = set()
    explicit = disc_cfg.get("niche_keywords", [])
    for k in explicit:
        keywords.add(k.lower().strip())

    for niche in disc_cfg.get("niches", []):
        for w in re.findall(r"[a-zA-Z0-9]+", niche.lower()):
            if len(w) > 2 and w not in stopwords:
                keywords.add(w)
    return keywords


def expand_niches_with_groq(niches: list[str]) -> list[str]:
    """Optionally uses free-tier Groq to brainstorm highly specific, non-random search queries."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return []

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        prompt = (
            f"Given these specific YouTube channel niches: {json.dumps(niches)}\n"
            "Generate 4 highly specific, high-converting YouTube search queries that will find the most viewed, "
            "highest quality videos specifically on these exact topics. Do NOT generate generic podcast or celebrity interview queries. "
            "Focus purely on high-retention educational, explainer, or tutorial content in these niches.\n"
            "Respond ONLY with a JSON object: {\"queries\": [\"...\"]}"
        )
        models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        data = None
        for model_name in models_to_try:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a precise YouTube content strategist. Output only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=400,
                )
                raw = response.choices[0].message.content or ""
                raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
                data = json.loads(raw)
                if data and data.get("queries"):
                    break
            except Exception:
                continue

        if not data:
            return []

        expanded = []
        if isinstance(data.get("queries"), list):
            expanded.extend(data["queries"])
        return expanded
    except Exception as e:
        print(f"  [Discovery] Groq niche expansion skipped: {e}")
        return []


def verify_niche_with_groq(candidates: list[dict], niches: list[str]) -> list[dict]:
    """Semantic Gatekeeper: Uses Groq to verify that candidate videos strictly match the channel niche."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or not candidates:
        return candidates

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        items_payload = [
            {"id": c["video_id"], "title": c["title"], "channel": str(c.get("channel", ""))}
            for c in candidates[:10]
        ]
        prompt = (
            f"You are a strict YouTube Channel Director. The channel niche is strictly: {json.dumps(niches)}.\n"
            f"Candidate Videos:\n{json.dumps(items_payload, indent=2)}\n\n"
            "Evaluate each candidate. Return ONLY a JSON array of video IDs that are genuinely, directly, "
            "and authentically on-topic for this exact niche. Discard any off-topic, celebrity gossip, or unrelated videos.\n"
            "Respond ONLY with a JSON array: [\"id1\", \"id2\", ...]"
        )
        models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        for model in models_to_try:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a strict content filter. Output ONLY a valid JSON array of IDs."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=400,
                )
                raw = resp.choices[0].message.content or ""
                raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
                json_match = re.search(r"\[.*\]", raw, re.DOTALL)
                if json_match:
                    raw = json_match.group(0)
                accepted_ids = json.loads(raw)
                if isinstance(accepted_ids, list) and accepted_ids:
                    id_set = set(accepted_ids)
                    verified = [c for c in candidates if c["video_id"] in id_set]
                    if verified:
                        print(f"  [Discovery] Groq verified {len(verified)}/{len(candidates)} candidates strictly match the niche.")
                        return verified
            except Exception:
                continue
    except Exception as e:
        print(f"  [Discovery] Groq niche verification skipped: {e}")

    return candidates


def filter_and_rank_candidates(
    candidates: list[dict],
    state: dict,
    min_views: int = 50_000,
    min_duration_sec: int = 600,
    max_duration_sec: int = 7200,
    blacklist_terms: list[str] | None = None,
    niche_keywords: set[str] | None = None,
) -> list[dict]:
    """Filters candidate videos for virality criteria, duration boundaries,
    blacklist safety (anti-DMCA protection), idempotency, and STRICT niche keyword relevance.
    """
    import math
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
        if duration is not None:
            if duration < min_duration_sec or duration > max_duration_sec:
                continue

        view_count = cand.get("view_count", 0)
        if min_views > 0 and view_count < min_views:
            continue

        # Strict Niche Relevance Filter: Reject candidates with 0 keyword hits in title/channel
        relevance_score = 1.0
        if niche_keywords:
            t_words = set(re.findall(r"[a-zA-Z0-9]+", cand.get("title", "").lower()))
            c_words = set(re.findall(r"[a-zA-Z0-9]+", str(cand.get("channel", "")).lower()))
            title_hits = len(t_words & niche_keywords)
            chan_hits = len(c_words & niche_keywords)

            # Hard Gate: Discard if zero relevance
            if title_hits == 0 and chan_hits == 0:
                continue
            relevance_score = (title_hits * 3.5) + (chan_hits * 1.5)

        cand["relevance_score"] = relevance_score
        seen_ids.add(v_id)
        valid.append(cand)

    # Sort primarily by Niche Relevance, secondarily by View Count
    def _rank_key(c: dict) -> float:
        views = max(c.get("view_count", 0), 1)
        rel = c.get("relevance_score", 1.0)
        return (rel * 25.0) + math.log10(views)

    valid.sort(key=_rank_key, reverse=True)
    return valid


def discover_and_select_videos(cfg: dict, state: dict) -> list[dict]:
    """Discovers viral creators and long-form videos based on config settings.
    Strictly filters targets to ensure 100% niche fidelity and eliminates random content.
    """
    disc_cfg = cfg.get("discovery", {})
    if not disc_cfg.get("enabled", False):
        return []

    niches = disc_cfg.get("niches", [])
    creators = disc_cfg.get("creators", [])
    blacklist_terms = [b.lower().strip() for b in disc_cfg.get("blacklist_terms", []) if b]
    min_views = disc_cfg.get("min_views", 60_000)
    min_dur_min = disc_cfg.get("min_duration_minutes", 6)
    max_dur_min = disc_cfg.get("max_duration_minutes", 120)
    max_per_run = disc_cfg.get("max_videos_per_run", 2)
    max_per_creator = disc_cfg.get("max_videos_per_creator", 1)

    min_dur_sec = int(min_dur_min * 60)
    max_dur_sec = int(max_dur_min * 60)

    niche_keywords = extract_niche_keywords(disc_cfg)
    all_candidates: list[dict] = []

    print("\n=== Running Viral Creator & Content Discovery ===")
    if niche_keywords:
        print(f"  [Discovery] Active Niche Filter Keywords: {len(niche_keywords)} terms loaded.")

    # 1. Search specified niche authority creators
    for creator in creators:
        clean_handle = creator.strip()
        print(f"  [Discovery] Checking authority creator: {clean_handle}")
        c_videos = get_creator_viral_videos(clean_handle, max_results=12)
        all_candidates.extend(c_videos)

    # 2. Search specified clean niche topics directly (no generic podcast append)
    for niche in niches:
        print(f"  [Discovery] Exploring clean niche query: '{niche}'")
        n_videos = search_youtube_videos(niche, max_results=15)
        all_candidates.extend(n_videos)

    # 3. Optional Groq topic query expansion if key is available
    groq_expanded = expand_niches_with_groq(niches)
    for q in groq_expanded[:3]:
        print(f"  [Discovery] Exploring AI-targeted niche query: '{q}'")
        g_videos = search_youtube_videos(q, max_results=12)
        all_candidates.extend(g_videos)

    print(f"  [Discovery] Gathered {len(all_candidates)} raw candidate entries across sources.")

    # 4. Strict filter and rank by niche relevance + virality
    ranked = filter_and_rank_candidates(
        all_candidates,
        state=state,
        min_views=min_views,
        min_duration_sec=min_dur_sec,
        max_duration_sec=max_dur_sec,
        blacklist_terms=blacklist_terms,
        niche_keywords=niche_keywords,
    )

    print(f"  [Discovery] {len(ranked)} candidates passed strict niche relevance & virality filters (views >= {min_views:,}, duration: {min_dur_min}m-{max_dur_min}m).")

    if not ranked:
        print("  [Discovery] No candidates passed strict niche filters with min_views. Broadening threshold...")
        ranked = filter_and_rank_candidates(
            all_candidates,
            state=state,
            min_views=max(10_000, min_views // 3),
            min_duration_sec=min_dur_sec,
            max_duration_sec=max_dur_sec,
            blacklist_terms=blacklist_terms,
            niche_keywords=niche_keywords,
        )

    # 5. Groq Semantic Verification (verifies top candidates genuinely belong to niche)
    verified_candidates = verify_niche_with_groq(ranked[:10], niches=niches)
    if not verified_candidates:
        verified_candidates = ranked

    # 6. Cap per creator and select top videos
    selected = []
    creator_counts: dict[str, int] = {}

    for cand in verified_candidates:
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
        rel_str = f"Rel: {s.get('relevance_score', 1.0):.1f}"
        print(f"  * Selected #{i+1} [{rel_str}]: '{safe_title}...' | Channel: {safe_channel} | Views: {views_str} | Dur: {dur_str}")

    return selected
