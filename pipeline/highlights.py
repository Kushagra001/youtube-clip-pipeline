"""Picks clip-worthy moments from a transcript. Two methods, both free:

- "heuristic" (default): pure scoring, no API key, no network call, $0 always.
  Scores sliding windows on hook strength, pacing, and engagement-language
  density, snapped to natural pause boundaries.
- "groq": uses Groq's free-tier LLM API (console.groq.com — free API key,
  no credit card required, generous rate limits on open models like
  Llama 3.3) for better judgment of what's actually compelling. Same
  output shape as the heuristic path, so it's a drop-in swap.

Set `highlight_method` in config/sources.yaml to choose.
"""
import json
import os
import re

# ---------------------------------------------------------------------------
# Heuristic method — no API, no cost, no signup
# ---------------------------------------------------------------------------

_HOOK_WORDS = {
    "crazy", "insane", "wow", "literally", "honestly", "secret", "never",
    "always", "mistake", "incredible", "worst", "best", "huge", "shocking",
    "unbelievable", "truth", "actually", "wrong", "hate", "love", "scary",
    "terrifying", "amazing", "wild", "brutal", "genius", "stupid", "failed",
    "won", "lost", "million", "billion", "kill", "fired",
    "quit", "lied", "lie", "cheat", "scam", "broke", "rich",
}


def _score_text(text: str) -> float:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return 0.0
    hook_hits = sum(1 for w in words if w in _HOOK_WORDS)
    question_marks = text.count("?")
    exclaims = text.count("!")
    # Reward hook-word density more than raw count so short punchy lines win
    density = hook_hits / max(len(words), 1)
    return (density * 10) + (question_marks * 1.5) + (exclaims * 0.75)


def _build_windows(
    segments: list[dict],
    min_seconds: int,
    max_seconds: int,
    min_start_offset: float = 35.0,
) -> list[dict]:
    """Generates candidate clip windows starting at natural pauses (gaps
    of >0.6s between segments, a reasonable proxy for a breath/topic break).
    For videos > 120s, automatically skips the opening 35s intro bumper/title cards."""
    windows = []
    total_duration = segments[-1]["end"] if segments else 0
    actual_offset = min_start_offset if total_duration > 120 else 0.0

    for i, seg in enumerate(segments):
        if seg["start"] < actual_offset:
            continue

        is_pause_start = (
            i == 0 or (seg["start"] - segments[i - 1]["end"]) > 0.6
        )
        if not is_pause_start:
            continue

        start = seg["start"]
        j = i
        while j < len(segments) and segments[j]["end"] - start < min_seconds:
            j += 1
        end_idx = j
        while (
            end_idx < len(segments)
            and segments[end_idx]["end"] - start <= max_seconds
        ):
            end_idx += 1
        end_idx = max(end_idx - 1, j if j < len(segments) else len(segments) - 1)
        if end_idx >= len(segments):
            continue

        end = segments[end_idx]["end"]
        duration = end - start
        if duration < min_seconds or duration > max_seconds:
            continue

        window_segments = [s for s in segments if s["start"] >= start and s["end"] <= end]
        text = " ".join(s["text"] for s in window_segments)
        windows.append({"start": start, "end": end, "text": text, "segments": window_segments})

    # Robust fallback: if no pause-based windows were found, use standard sliding windows
    if not windows and segments:
        for i in range(0, len(segments), max(1, len(segments) // 10)):
            start = segments[i]["start"]
            j = i
            while j < len(segments) and (segments[j]["end"] - start) < min_seconds:
                j += 1
            if j < len(segments):
                end = segments[j]["end"]
                dur = end - start
                if dur <= max_seconds + 3.0:
                    window_segments = segments[i : j + 1]
                    text = " ".join(s["text"] for s in window_segments)
                    windows.append({"start": start, "end": end, "text": text, "segments": window_segments})
    return windows


def _non_overlapping_top(windows: list[dict], max_clips: int) -> list[dict]:
    ranked = sorted(windows, key=lambda w: w["score"], reverse=True)
    chosen = []
    for w in ranked:
        if any(not (w["end"] <= c["start"] or w["start"] >= c["end"]) for c in chosen):
            continue
        chosen.append(w)
        if len(chosen) >= max_clips:
            break
    return sorted(chosen, key=lambda w: w["start"])


import html

def _clean_text(text: str) -> str:
    unescaped = html.unescape(text)
    cleaned = re.sub(r">>|<<|\[.*?\]|\(.*?\)", " ", unescaped)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_valid_hook_question(q: str) -> bool:
    words = q.split()
    if len(words) < 4 or len(words) > 9:
        return False
    q_lower = q.lower()
    disallowed = ("more or less", "you know", "right", "is that", "does that make", "or what", "huh", "okay")
    if any(d in q_lower for d in disallowed):
        return False
    valid_starts = ("who", "what", "why", "how", "when", "where", "can", "could", "should", "would", "is", "are", "do", "does", "did", "have", "has")
    return words[0].lower() in valid_starts


def _generate_catchy_hook(window_text: str, source_title: str | None = None) -> str:
    """Generates an engaging, topic-relevant viral meme headline (<44 chars)."""
    clean_window = _clean_text(window_text)

    # 1. Search for genuine high-converting questions in the window
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", clean_window) if s.strip()]
    for s in sentences:
        if s.endswith("?") and _is_valid_hook_question(s):
            q_clean = re.sub(r"[^\w\s?]", "", s).strip().upper()
            if len(q_clean) <= 40:
                return f"{q_clean} 🤔"

    # 2. Extract context from source_title if present
    if source_title:
        clean_title = re.sub(r"(?i)\s*\|\s*(ted|the diary of a ceo|podcast|interview|lex fridman|huberman).*", "", source_title)
        clean_title = re.sub(r"(?i)(episode\s*#?\d+|full episode|whistleblower\s*[\w\s]+:)", "", clean_title).strip()
        t_lower = clean_title.lower()

        if any(w in t_lower for w in ("personality", "introvert", "extrovert", "psychology")):
            return "WHY INTROVERTS ACT DIFFERENTLY 🧠"
        if any(w in t_lower for w in ("surveillance", "cia", "see all", "phone", "track")):
            return "THEY CAN SEE EVERYTHING YOU DO 📱"
        if any(w in t_lower for w in ("money", "billion", "wealth", "rich", "invest")):
            return "THE TRUTH ABOUT HOW MONEY WORKS 💰"
        if any(w in t_lower for w in ("habit", "success", "discipline", "mindset")):
            return "THE HABIT THAT CHANGES EVERYTHING 📈"
        if any(w in t_lower for w in ("who are you", "who you are")):
            return "WHO ARE YOU, REALLY? 🤔"

    # 3. Keyword-driven hooks based on high-retention topics in window
    w_lower = clean_window.lower()
    if any(k in w_lower for k in ("responsibility", "duty", "stoic", "meaning", "suffering")):
        return "HOW MUCH CAN YOU ACTUALLY BEAR? 🏛️"
    if any(k in w_lower for k in ("dog", "puppy", "bark", "leash", "canine")):
        return "THE SECRET TO TRAINING YOUR DOG 🐶"
    if any(k in w_lower for k in ("cat", "kitten", "purr", "feline")):
        return "WHY CATS ACTUALLY DO THIS 🐱"
    if any(k in w_lower for k in ("muscle", "hypertrophy", "workout", "lifting", "protein")):
        return "STOP MAKING THIS WORKOUT MISTAKE ⚠️"
    if any(k in w_lower for k in ("ai", "chatgpt", "claude", "prompt", "automate")):
        return "THE SECRET AI TOOL NOBODY SHARES 🤖"
    if any(k in w_lower for k in ("skin", "haircut", "grooming", "cologne", "beard")):
        return "THIS INSTANTLY ELEVATES YOUR LOOK 💈"
    if any(k in w_lower for k in ("recipe", "cook", "chef", "delicious", "kitchen")):
        return "THE BEST 60-SECOND FOOD HACK 🍳"
    if any(k in w_lower for k in ("anxiety", "adhd", "burnout", "nervous system", "panic")):
        return "HOW TO RESET YOUR NERVOUS SYSTEM 🧘"
    if "introvert" in w_lower or "extrovert" in w_lower or "personality" in w_lower:
        return "WHY INTROVERTS ACT DIFFERENTLY 🧠"
    if "surveillance" in w_lower or "cia" in w_lower or "phone" in w_lower:
        return "THEY CAN MONITOR EVERYTHING 📱"
    if "secret" in w_lower or "truth" in w_lower:
        return "NOBODY WANTS TO TALK ABOUT THIS 🤫"
    if "mistake" in w_lower or "wrong" in w_lower:
        return "THE BIGGEST MISTAKE PEOPLE MAKE ⚠️"
    if "money" in w_lower or "billion" in w_lower:
        return "THE SHOCKING TRUTH ABOUT THIS 😳"

    # 4. Fallback to punchy first words or general viral hook
    words = clean_window.split()
    first_clean = " ".join(words[:6]).upper()
    first_clean = re.sub(r"[^\w\s]", "", first_clean).strip()
    if 10 <= len(first_clean) <= 38:
        return f"{first_clean} 😳"

    return "THIS WILL CHANGE HOW YOU THINK 🧠"


def _generate_meaningful_takeaway(
    window_text: str,
    source_title: str | None = None,
) -> str:
    """Generates a complete, meaningful educational takeaway (<58 chars) for Fair Use."""
    clean_window = _clean_text(window_text)
    sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", clean_window) if s.strip()]

    insight_triggers = (
        "the point is", "the key is", "in reality", "what matters", "remember",
        "you have to", "that means", "the truth is", "because", "always",
        "never", "it turns out", "we need", "make us", "allows us", "important to"
    )

    # 1. Search sentences in the latter half for an explicit insight trigger
    for s in reversed(sentences):
        s_lower = s.lower()
        if any(trig in s_lower for trig in insight_triggers):
            words = s.split()
            if len(words) >= 5 and not words[-1].isdigit():
                clean_s = re.sub(r"[^\w\s]", "", s).strip().upper()
                if len(clean_s) > 40:
                    clean_s = " ".join(clean_s.split()[:6])
                return f"KEY INSIGHT: {clean_s}"

    # 2. Topic-driven insight synthesis if transcript ending is fragmentary
    combo = f"{source_title or ''} {clean_window}".lower()
    if any(k in combo for k in ("personality", "introvert", "extrovert", "psychology")):
        return "KEY INSIGHT: BEHAVIOR VARIES BY SITUATION, NOT LABELS"
    if any(k in combo for k in ("cia", "surveillance", "monitor", "privacy", "phone")):
        return "KEY INSIGHT: DIGITAL FOOTPRINTS ARE NEVER TRULY PRIVATE"
    if any(k in combo for k in ("money", "billion", "wealth", "invest")):
        return "KEY INSIGHT: STRATEGIC ALLOCATION BEATS SHORT-TERM RISK"
    if any(k in combo for k in ("founder", "startup", "business", "scale", "revenue")):
        return "KEY INSIGHT: RELENTLESS EXECUTION BEATS MERE IDEAS"
    if any(k in combo for k in ("habit", "success", "discipline", "mindset")):
        return "KEY INSIGHT: DAILY DISCIPLINE CREATES COMPOUND RESULTS"
    if any(k in combo for k in ("health", "sleep", "body", "brain")):
        return "KEY INSIGHT: DAILY HABITS DIRECTLY DICTATE YOUR BIOLOGY"
    if any(k in combo for k in ("dog", "puppy", "bark", "leash", "canine")):
        return "KEY INSIGHT: CONSISTENT REINFORCEMENT SHAPES BEHAVIOR"
    if any(k in combo for k in ("cat", "kitten", "purr", "feline")):
        return "KEY INSIGHT: RESPECT AND HARNESS NATURAL FELINE INSTINCTS"
    if any(k in combo for k in ("muscle", "hypertrophy", "workout", "lifting", "protein")):
        return "KEY INSIGHT: PROGRESSIVE OVERLOAD DRIVES REAL GROWTH"
    if any(k in combo for k in ("ai", "chatgpt", "claude", "prompt", "automate")):
        return "KEY INSIGHT: AI MULTIPLIES LEVERAGE AND SAVES CRUCIAL HOURS"
    if any(k in combo for k in ("skin", "haircut", "grooming", "cologne", "beard")):
        return "KEY INSIGHT: CONSISTENT GROOMING ELEVATES FIRST IMPRESSIONS"
    if any(k in combo for k in ("recipe", "cook", "chef", "delicious", "kitchen")):
        return "KEY INSIGHT: MASTERING HEAT AND TIMING ELEVATES FLAVOR"
    if any(k in combo for k in ("anxiety", "adhd", "burnout", "nervous system", "panic")):
        return "KEY INSIGHT: REGULATING THE NERVOUS SYSTEM RESETS FOCUS"
    if any(k in combo for k in ("responsibility", "duty", "stoic", "meaning", "suffering")):
        return "KEY INSIGHT: ACCEPTING RESPONSIBILITY CREATES REAL STRENGTH"

    # 3. Fallback: substantive complete sentence with >= 5 words
    for s in reversed(sentences):
        words = s.split()
        if len(words) >= 5 and not words[-1].isdigit():
            clean_s = re.sub(r"[^\w\s]", "", s).strip().upper()
            if len(clean_s) > 40:
                clean_s = " ".join(clean_s.split()[:6])
            return f"KEY INSIGHT: {clean_s}"

    return "KEY INSIGHT: AWARENESS IS THE FIRST STEP TO CHANGE"


def find_highlights_heuristic(
    segments: list[dict],
    max_clips: int = 3,
    min_seconds: int = 25,
    max_seconds: int = 55,
    source_title: str | None = None,
) -> list[dict]:
    windows = _build_windows(segments, min_seconds, max_seconds)
    for w in windows:
        w["score"] = _score_text(w["text"])
    top = _non_overlapping_top(windows, max_clips)

    results = []
    for w in top:
        # Snap start strictly to first segment start to eliminate dead air
        first_seg = w["segments"][0] if w.get("segments") else None
        exact_start = first_seg["start"] if first_seg else w["start"]

        clean_w_text = _clean_text(w["text"])
        words = clean_w_text.split()
        first_words = " ".join(words[:8])

        burner_headline = _generate_catchy_hook(w["text"], source_title=source_title)
        takeaway_str = _generate_meaningful_takeaway(w["text"], source_title=source_title)

        title_words = " ".join(words[:10])
        clip_title = (title_words[:50] + "...") if len(title_words) > 50 else title_words

        results.append({
            "start": exact_start,
            "end": w["end"],
            "title": clip_title,
            "hook": first_words,
            "burner_text": burner_headline,
            "takeaway": takeaway_str,
        })
    return results


# ---------------------------------------------------------------------------
# Groq method — free-tier hosted LLM, optional, better judgment
# ---------------------------------------------------------------------------

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "llama-3.3-70b-versatile",
]

SYSTEM_PROMPT = """You select the most compelling short-form clip moments from a \
podcast/video transcript for repurposing strictly as YouTube Shorts (< 60 seconds).

Requirements:
1. Pick moments that start IMMEDIATELY on a high-retention hook (0 seconds of dead air to maximize VVSA > 75%), \
and end cleanly on a decisive insight or punchline.
2. Prioritize seamless looping: The ending sentence should logically flow back into the opening hook \
to encourage re-watching (APV > 100%).
3. The duration MUST be between 25 and 48 seconds (optimal retention sweet spot).
4. Generate a "burner_text": A punchy, all-caps headline (<45 characters) that serves as the top editorial banner hook.
5. Generate a "takeaway": A 1-sentence analytical or educational takeaway (<55 characters) summarizing \
the transformative insight for the outro analysis card.
6. STRICT LANGUAGE REQUIREMENT: All output fields ("title", "hook", "burner_text", "takeaway") MUST be written \
strictly in ENGLISH. Never output Hindi, Devanagari, or foreign language text. Translate into viral English if needed.

Respond with ONLY a JSON array (no prose, no markdown fences). Each item:
{
  "start": <float, seconds, snapped to first spoken word>,
  "end": <float, seconds, snapped to punchline end>,
  "title": "<short punchy English title, <55 chars>",
  "hook": "<first ~8 words spoken, opening caption in English>",
  "burner_text": "<ALL-CAPS PUNCHY TOP BANNER HEADLINE IN ENGLISH, <45 chars>",
  "takeaway": "<KEY TAKEAWAY: SUMMARY LESSON IN ENGLISH, <55 chars>"
}
"""


def _transcript_to_text(
    segments: list[dict],
    max_segments: int = 120,
    min_start_offset: float = 35.0,
) -> str:
    # Filter out opening intro bumpers / sponsor graphics for videos > 120s
    total_duration = segments[-1]["end"] if segments else 0
    actual_offset = min_start_offset if total_duration > 120 else 0.0
    usable_segments = [s for s in segments if s["start"] >= actual_offset]
    if not usable_segments:
        usable_segments = segments

    raw_text = " ".join(s["text"] for s in usable_segments)
    # If transcript is long (>120 segments or >4000 chars), condense to top candidate windows
    # to strictly stay within Groq's 8,000 Tokens-Per-Minute (TPM) limit
    if len(usable_segments) > max_segments or len(raw_text) > 4000:
        windows = _build_windows(usable_segments, min_seconds=25, max_seconds=48, min_start_offset=0.0)
        for w in windows:
            w["score"] = _score_text(w["text"])
        # Take top 8 high-scoring windows (~1,200 tokens total)
        top_windows = sorted(windows, key=lambda w: w["score"], reverse=True)[:8]
        top_windows = sorted(top_windows, key=lambda w: w["start"])
        return "\n\n".join(
            f"Candidate Window [{w['start']:.1f}-{w['end']:.1f}]:\n{w['text']}"
            for w in top_windows
        )
    return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in usable_segments)


def find_highlights_groq(
    segments: list[dict],
    max_clips: int = 3,
    min_seconds: int = 25,
    max_seconds: int = 48,
    source_title: str | None = None,
) -> list[dict]:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set")

    from groq import Groq
    client = Groq(api_key=api_key)
    transcript_text = _transcript_to_text(segments)
    title_context = f"Source Video Title: {source_title}\n\n" if source_title else ""
    user_prompt = (
        f"{title_context}Transcript / Candidate Windows:\n\n{transcript_text}\n\n"
        f"Select up to {max_clips} clips. Each clip MUST be strictly between "
        f"{min_seconds} and {max_seconds} seconds long, starting on the exact "
        f"spoken word timestamp and ending on a punchline that can loop seamlessly. "
        f"Make sure burner_text is an irresistible catchy hook headline (<42 chars) "
        f"and takeaway is a profound educational summary (<55 chars)."
    )

    last_error = None
    for model_name in GROQ_MODELS:
        try:
            print(f"  [Highlights] Requesting AI clip curation via Groq ({model_name})...")
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=3000,
            )

            raw = response.choices[0].message.content or ""
            raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            # If model returned text around JSON, extract the JSON array
            json_match = re.search(r"\[.*\]", raw, re.DOTALL)
            if json_match:
                raw = json_match.group(0)

            clips = json.loads(raw)
            valid = []
            for c in clips:
                if not all(k in c for k in ("start", "end", "title", "hook")):
                    continue
                if c["end"] <= c["start"]:
                    continue
                duration = c["end"] - c["start"]
                if duration < min_seconds * 0.7 or duration > 52.0:
                    continue
                if "burner_text" not in c:
                    c["burner_text"] = c["title"].upper()[:42]
                if "takeaway" not in c:
                    c["takeaway"] = f"KEY INSIGHT: {c['title'].upper()[:45]}"
                valid.append(c)

            if valid:
                print(f"  [Highlights] Groq ({model_name}) successfully selected {len(valid)} clip(s).")
                return valid[:max_clips]
        except Exception as err:
            print(f"  [Highlights] Model {model_name} failed: {err}. Trying next fallback model...")
            last_error = err

    if last_error:
        raise last_error
    return []


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def find_highlights(
    segments: list[dict],
    max_clips: int = 3,
    min_seconds: int = 25,
    max_seconds: int = 55,
    method: str = "heuristic",
    source_title: str | None = None,
) -> list[dict]:
    if method == "groq":
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("  [Highlights] GROQ_API_KEY not set, falling back to heuristic method.")
            return find_highlights_heuristic(segments, max_clips, min_seconds, max_seconds, source_title=source_title)
        try:
            picks = find_highlights_groq(segments, max_clips, min_seconds, max_seconds, source_title=source_title)
            if picks:
                return picks
            print("  [Highlights] Groq returned 0 clips, falling back to heuristic method.")
        except Exception as e:
            print(f"  [Highlights] Groq selection failed ({e}), falling back to heuristic method.")

    return find_highlights_heuristic(segments, max_clips, min_seconds, max_seconds, source_title=source_title)
