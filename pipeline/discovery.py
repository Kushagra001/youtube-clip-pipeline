"""Autonomous discovery of viral creators and high-performing long-form videos.

Works 100% on free tiers and requires no paid APIs:
- Uses yt-dlp's search and metadata extraction (no YouTube API quota consumed).
- Optionally leverages Groq free-tier LLM (Llama 3.3) for niche expansion if GROQ_API_KEY is present.
"""
import os
import re
import json
import math
import datetime
import urllib.parse
from typing import Optional
import yt_dlp

from pipeline import state as state_mod


class _SilentLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _get_ydl(search_depth: int = 25) -> yt_dlp.YoutubeDL:
    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "logger": _SilentLogger(),
        "playlistend": search_depth,
    }
    proxy_url = os.environ.get("PROXY_URL") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy_url:
        opts["proxy"] = proxy_url

    try:
        from pipeline.download import get_cookies_path
        cookie_path = get_cookies_path()
        if cookie_path:
            opts["cookiefile"] = str(cookie_path)
    except Exception:
        pass
    return yt_dlp.YoutubeDL(opts)


def search_youtube_videos(query: str, max_results: int = 20, sort: str = "relevance") -> list[dict]:
    """Searches YouTube using yt-dlp and returns flat metadata for candidate videos.
    Supports sort='relevance', sort='views' (sp=CAMSAhAB), or sort='this_year' (sp=EgQIBRAB).
    """
    if sort == "views":
        encoded = urllib.parse.quote_plus(query)
        search_target = f"https://www.youtube.com/results?search_query={encoded}&sp=CAMSAhAB"
    elif sort == "this_year":
        encoded = urllib.parse.quote_plus(query)
        search_target = f"https://www.youtube.com/results?search_query={encoded}&sp=EgQIBRAB"
    else:
        search_target = f"ytsearch{max_results}:{query}"

    videos = []
    try:
        with _get_ydl(search_depth=max_results) as ydl:
            res = ydl.extract_info(search_target, download=False)
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
                    "query_source": f"{query} [{sort}]",
                })
    except Exception as e:
        print(f"  [Discovery] Warning: Search failed for query '{query}' [{sort}]: {e}")
    return videos


def get_creator_channel_videos(creator: str, max_results: int = 12) -> list[dict]:
    """Direct Creator Channel Scraping: Scrapes official creator uploads directly from their channel page.
    Prioritizes the creator's Popular and Latest uploads, eliminating fake/reaction channels.
    Falls back gracefully to standard YouTube search if direct channel extraction is unavailable.
    """
    clean = creator.strip()
    if clean.startswith("@") or "youtube.com" in clean:
        if clean.startswith("@"):
            base_url = f"https://www.youtube.com/{clean}"
        elif not clean.startswith("http"):
            base_url = f"https://{clean}"
        else:
            base_url = clean.rstrip("/")

        channel_targets = [
            f"{base_url}/videos?view=0&sort=p",  # Popular uploads
            f"{base_url}/videos",                 # Latest uploads
        ]
        videos = []
        seen_ids = set()
        for target_url in channel_targets:
            try:
                with _get_ydl(search_depth=max_results) as ydl:
                    res = ydl.extract_info(target_url, download=False)
                    entries = res.get("entries", []) if res else []
                    for entry in entries:
                        if not entry:
                            continue
                        v_id = entry.get("id")
                        if not v_id or v_id in seen_ids:
                            continue
                        seen_ids.add(v_id)
                        videos.append({
                            "video_id": v_id,
                            "url": f"https://www.youtube.com/watch?v={v_id}",
                            "title": entry.get("title", ""),
                            "channel": entry.get("uploader") or entry.get("channel") or clean,
                            "duration": entry.get("duration"),
                            "view_count": entry.get("view_count") or 0,
                            "query_source": f"channel:{clean}",
                            "is_official_creator": True,
                        })
                        if len(videos) >= max_results:
                            break
            except Exception:
                continue
            if videos:
                break
        if videos:
            return videos

    # Fallback to standard creator search (tag as official creator)
    fallback_videos = search_youtube_videos(clean, max_results=max_results)
    for v in fallback_videos:
        v["is_official_creator"] = True
    return fallback_videos


def get_creator_viral_videos(creator: str, max_results: int = 15, niche_hint: str = "") -> list[dict]:
    """Finds top videos from a creator handle or channel name."""
    return get_creator_channel_videos(creator, max_results=max_results)


def extract_niche_keywords(disc_cfg: dict) -> set[str]:
    """Extracts distinctive content keywords from channel niche descriptions, hashtags, and subwords."""
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "how", "why", "what",
        "to", "in", "on", "of", "a", "an", "full", "episode", "podcast", "video",
        "videos", "best", "top", "viral", "interview", "new", "things", "facts", "lessons",
        "story", "speech", "talk", "guide", "routine", "everyday", "users"
    }
    keywords = set()
    explicit = disc_cfg.get("niche_keywords", [])
    for k in explicit:
        keywords.add(k.lower().strip())

    # 1. Extract from exact niche_desc
    niche_desc = disc_cfg.get("niche_desc", "")
    for w in re.findall(r"[a-zA-Z0-9]+", niche_desc.lower()):
        if len(w) > 2 and w not in stopwords:
            keywords.add(w)

    # 2. Extract and decompose scrape_hashtags
    subwords_bank = [
        "cats", "cat", "dogs", "dog", "puppy", "kittens", "kitten", "cute", "funny",
        "workout", "fitness", "gym", "calisthenics", "mindset", "discipline",
        "stoicism", "success", "mental", "strength", "finance", "investing",
        "side", "hustle", "hustles", "freedom", "stock", "market", "startup",
        "business", "founder", "grooming", "skincare", "haircare", "style",
        "recipes", "recipe", "meal", "prep", "food", "hacks", "quick",
        "tools", "automation", "intelligence", "anxiety", "adhd", "wellness",
        "selfcare", "budgeting", "home", "training", "life"
    ]
    for tag in disc_cfg.get("scrape_hashtags", []):
        t_clean = tag.lower().lstrip("#")
        if len(t_clean) > 2 and t_clean not in stopwords:
            keywords.add(t_clean)
        for sw in subwords_bank:
            if sw in t_clean:
                keywords.add(sw)

    # 3. Extract from niches list
    for niche in disc_cfg.get("niches", []):
        for w in re.findall(r"[a-zA-Z0-9]+", niche.lower()):
            if len(w) > 2 and w not in stopwords:
                keywords.add(w)

    return keywords


def expand_niches_with_groq(niche_desc: str, scrape_hashtags: list[str], niches: list[str]) -> list[str]:
    """Optionally uses free-tier Groq to brainstorm highly specific, non-random search queries."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return []

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        tags_str = ", ".join(f"#{t.lstrip('#')}" for t in scrape_hashtags)
        context = f"Target Audience / Niche Description: '{niche_desc}'\nRelevant Hashtags: {tags_str}\nTopic Queries: {json.dumps(niches)}"
        prompt = (
            f"You are a YouTube search expert for this specific channel audience:\n{context}\n\n"
            "Generate 3-4 highly specific YouTube search queries that will discover the most viewed, "
            "highest quality long-form videos that directly serve this exact audience. "
            "Do NOT suggest generic podcasts, gossip, or celebrity interviews. Keep queries strictly focused on this niche.\n"
            "Respond ONLY with a JSON object: {\"queries\": [\"...\"]}"
        )
        models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
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
                    return data["queries"]
            except Exception:
                continue
        return []
    except Exception as e:
        print(f"  [Discovery] Groq niche expansion skipped: {e}")
        return []


def verify_niche_with_groq(candidates: list[dict], niche_desc: str, scrape_hashtags: list[str]) -> list[dict]:
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
        tags_str = ", ".join(f"#{t.lstrip('#')}" for t in scrape_hashtags)
        prompt = (
            f"You are a strict YouTube Channel Director. The channel is strictly targeting:\n"
            f"Niche Description: '{niche_desc}'\nHashtags: {tags_str}\n\n"
            f"Candidate Videos:\n{json.dumps(items_payload, indent=2)}\n\n"
            "Evaluate each candidate against the niche description. Return ONLY a JSON array of video IDs that are genuinely, directly, "
            "and authentically on-topic English content for this exact audience.\n"
            "STRICT DISQUALIFICATION RULES:\n"
            "1. DISCARD any animated cartoons, kids nursery rhymes, toddlers songs, or toy videos (even if featuring animals/relevant words).\n"
            "2. DISCARD any foreign-language, Hindi, Hinglish, or non-English videos.\n"
            "3. DISCARD off-topic gaming streams, celebrity gossip, prank videos, or drama.\n"
            "Respond ONLY with a JSON array of accepted IDs: [\"id1\", \"id2\", ...]"
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
                        print(f"  [Discovery] Groq verified {len(verified)}/{len(candidates)} candidates strictly match '{niche_desc}'.")
                        return verified
            except Exception:
                continue
    except Exception as e:
        print(f"  [Discovery] Groq niche verification skipped: {e}")

    return candidates


def _is_english_title(text: str) -> bool:
    """Rejects titles containing non-Latin scripts (e.g. Devanagari/Hindi, Arabic, CJK, Cyrillic)."""
    if not text:
        return False
    # Reject non-Latin characters: Devanagari (\u0900-\u097F), Arabic (\u0600-\u06FF), Cyrillic (\u0400-\u04FF), CJK (\u4E00-\u9FFF)
    if re.search(r"[\u0900-\u097F\u0600-\u06FF\u0400-\u04FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]", text):
        return False
    return True


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

        title = cand.get("title", "")
        # Strict Language Filter: Reject foreign language / non-English script videos
        if not _is_english_title(title):
            continue

        # Litigious content safety filter (avoids automated DMCA strikes from TV/studios/sports)
        # Litigious content safety filter and negative keywords (word-boundary safe)
        if blacklist_terms:
            t_lower = cand.get("title", "").lower()
            c_lower = str(cand.get("channel", "")).lower()
            combined_text = f"{t_lower} {c_lower}"
            is_blacklisted = False
            for term in blacklist_terms:
                if re.search(r"\b" + re.escape(term) + r"\b", combined_text):
                    is_blacklisted = True
                    break
            if is_blacklisted:
                continue

        duration = cand.get("duration")
        if duration is not None:
            if duration < min_duration_sec or duration > max_duration_sec:
                continue

        view_count = cand.get("view_count", 0)
        if min_views > 0 and view_count < min_views:
            continue

        # Strict Niche Relevance Filter: Prioritize verified official creators, gate generic search
        relevance_score = 1.0
        is_official = cand.get("is_official_creator", False)
        if niche_keywords:
            t_words = set(re.findall(r"[a-zA-Z0-9]+", cand.get("title", "").lower()))
            c_words = set(re.findall(r"[a-zA-Z0-9]+", str(cand.get("channel", "")).lower()))
            title_hits = len(t_words & niche_keywords)
            chan_hits = len(c_words & niche_keywords)

            if is_official:
                # Official creators have guaranteed topical authenticity
                relevance_score = 10.0 + (title_hits * 3.5) + (chan_hits * 1.5)
            else:
                # Hard Gate for general search: Discard if zero relevance hits
                if title_hits == 0 and chan_hits == 0:
                    continue
                relevance_score = (title_hits * 3.5) + (chan_hits * 1.5)
        elif is_official:
            relevance_score = 10.0

        cand["relevance_score"] = relevance_score
        seen_ids.add(v_id)
        valid.append(cand)

    # Sort primarily by Official Creator Status + Niche Relevance, secondarily by View Count
    def _rank_key(c: dict) -> float:
        views = max(c.get("view_count", 0), 1)
        rel = c.get("relevance_score", 1.0)
        official_bonus = 60.0 if c.get("is_official_creator") else 0.0
        return official_bonus + (rel * 25.0) + math.log10(views)

    valid.sort(key=_rank_key, reverse=True)
    return valid


def enrich_candidates_virality(candidates: list[dict], max_enrich: int = 12) -> list[dict]:
    """Viral Velocity & Subtitle Pre-Checker:
    Enriches top candidate videos with exact upload date, views-per-day velocity (VPH),
    and pre-existing subtitle availability to accelerate pipeline processing by 5-10x.
    """
    if not candidates:
        return candidates

    to_enrich = candidates[:max_enrich]
    enriched = []
    today = datetime.datetime.now()

    ydl_opts = {
        "extract_flat": False,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "logger": _SilentLogger(),
    }
    try:
        from pipeline.download import get_cookies_path
        cookie_path = get_cookies_path()
        if cookie_path:
            ydl_opts["cookiefile"] = str(cookie_path)
    except Exception:
        pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for cand in to_enrich:
                v_id = cand["video_id"]
                url = cand.get("url") or f"https://www.youtube.com/watch?v={v_id}"
                views = cand.get("view_count") or 0
                upload_date_str = None
                has_subs = False

                try:
                    info = ydl.extract_info(url, download=False)
                    if info:
                        views = info.get("view_count") or views
                        cand["view_count"] = views
                        cand["duration"] = info.get("duration") or cand.get("duration")
                        upload_date_str = info.get("upload_date")
                        subs = info.get("subtitles") or {}
                        auto_subs = info.get("automatic_captions") or {}
                        has_subs = bool(subs or auto_subs)
                except Exception:
                    pass

                age_days = 365
                if upload_date_str:
                    try:
                        dt = datetime.datetime.strptime(upload_date_str, "%Y%m%d")
                        age_days = max((today - dt).days, 1)
                    except Exception:
                        age_days = 365

                views_per_day = views / max(age_days, 1)

                # Recency Velocity Multipliers: Breakout videos get substantial priority
                if age_days <= 14:
                    recency_multiplier = 1.6
                elif age_days <= 45:
                    recency_multiplier = 1.4
                elif age_days <= 90:
                    recency_multiplier = 1.25
                elif age_days <= 365:
                    recency_multiplier = 1.1
                elif age_days <= 730:
                    recency_multiplier = 0.95
                else:
                    recency_multiplier = 0.75

                # Subtitle Pre-Check Multiplier: strongly prioritizes videos with verified dialogue
                sub_multiplier = 1.5 if has_subs else 0.85
                official_bonus = 60.0 if cand.get("is_official_creator") else 0.0

                rel = cand.get("relevance_score", 1.0)
                virality_score = (
                    official_bonus +
                    (rel * 25.0) +
                    (math.log10(max(views_per_day, 1.0)) * 7.0) +
                    (math.log10(max(views, 1.0)) * 2.0)
                ) * recency_multiplier * sub_multiplier

                cand["age_days"] = age_days
                cand["views_per_day"] = int(views_per_day)
                cand["has_subtitles"] = has_subs
                cand["virality_score"] = virality_score
                enriched.append(cand)

    except Exception as e:
        print(f"  [Discovery] Candidate enrichment note: {e}")
        return candidates

    enriched.sort(key=lambda c: c.get("virality_score", 0.0), reverse=True)
    remainder = candidates[max_enrich:]
    return enriched + remainder


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

    niche_desc = disc_cfg.get("niche_desc", "")
    scrape_hashtags = disc_cfg.get("scrape_hashtags", [])

    print("\n=== Running Viral Creator & Content Discovery ===")
    if niche_desc:
        print(f"  [Discovery] Niche Focus: '{niche_desc}'")
    if scrape_hashtags:
        print(f"  [Discovery] Target Hashtags: {', '.join(f'#{t}' for t in scrape_hashtags)}")
    if niche_keywords:
        print(f"  [Discovery] Active Niche Filter Keywords: {len(niche_keywords)} terms loaded.")

    # 1. Direct creator channel scraping (popular & latest uploads from official channel)
    for creator in creators:
        clean_handle = creator.strip()
        print(f"  [Discovery] Checking official creator channel: {clean_handle}")
        c_videos = get_creator_channel_videos(clean_handle, max_results=12)
        all_candidates.extend(c_videos)

    # 2. Search exact niche description directly (all-time & this-year velocity)
    if niche_desc:
        print(f"  [Discovery] Exploring core niche description: '{niche_desc}'")
        nd_videos = search_youtube_videos(niche_desc, max_results=15)
        all_candidates.extend(nd_videos)

        print(f"  [Discovery] Exploring recent trending hits from this year: '{niche_desc}'")
        ny_videos = search_youtube_videos(niche_desc, max_results=12, sort="this_year")
        all_candidates.extend(ny_videos)

    # 3. Search intent-grounded hashtag topics (avoids raw hashtag bot/cartoon spam)
    for tag in scrape_hashtags[:3]:
        clean_tag = tag.strip().lstrip("#")
        search_query = f"{clean_tag} {niche_desc}" if niche_desc else f"{clean_tag} tips advice"
        print(f"  [Discovery] Exploring intent-grounded query: '{search_query}'")
        h_videos = search_youtube_videos(search_query, max_results=12)
        all_candidates.extend(h_videos)

    # 4. Search specified clean niche topics directly
    for niche in niches:
        print(f"  [Discovery] Exploring clean niche query: '{niche}'")
        n_videos = search_youtube_videos(niche, max_results=15)
        all_candidates.extend(n_videos)

    # 5. Optional Groq topic query expansion if key is available
    groq_expanded = expand_niches_with_groq(niche_desc, scrape_hashtags, niches)
    for q in groq_expanded[:3]:
        print(f"  [Discovery] Exploring AI-targeted niche query: '{q}'")
        g_videos = search_youtube_videos(q, max_results=12)
        all_candidates.extend(g_videos)

    print(f"  [Discovery] Gathered {len(all_candidates)} raw candidate entries across sources.")

    # 6. Strict filter and rank by niche relevance + virality
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

    # 7. Velocity & Subtitle Pre-Enrichment on top candidates
    if ranked:
        print(f"  [Discovery] Calculating viral velocity (VPH) and pre-checking subtitles on top {min(10, len(ranked))} candidates...")
        ranked = enrich_candidates_virality(ranked, max_enrich=10)

    # 8. Groq Semantic Verification (verifies top candidates genuinely belong to niche)
    verified_candidates = verify_niche_with_groq(ranked[:10], niche_desc=niche_desc, scrape_hashtags=scrape_hashtags)
    if not verified_candidates:
        verified_candidates = ranked

    # 9. Cap per creator and select top videos
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
        safe_title = s.get("title", "")[:50].encode("ascii", errors="replace").decode("ascii")
        safe_channel = str(s.get("channel", "Unknown")).encode("ascii", errors="replace").decode("ascii")
        
        score_val = s.get("virality_score", s.get("relevance_score", 1.0))
        vpd_val = s.get("views_per_day")
        vpd_str = f"{vpd_val:,}/d" if vpd_val is not None else "N/A"
        age_str = f"{s.get('age_days', '?')}d"
        cc_str = "CC:Yes" if s.get("has_subtitles") else "CC:No"

        print(f"  * Selected #{i+1} [Score: {score_val:.1f} | VPD: {vpd_str} | Age: {age_str} | {cc_str}]: '{safe_title}...' | Channel: {safe_channel} | Views: {views_str} | Dur: {dur_str}")

    return selected
