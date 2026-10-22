"""Produces a timestamped transcript: [{start, end, text}, ...]

Prefers YouTube's own captions (fast, free) with precise word-level synchronization,
HTML unescaping, and speaker-marker cleanup. Falls back to local transcription
with faster-whisper when no captions exist.
"""
import re
import html
from pathlib import Path


def _parse_vtt_timestamp(ts: str) -> float:
    # Handles 00:01:23.456, 01:23.456, and comma decimals (00:01:23,456)
    clean_ts = ts.strip().replace(",", ".")
    parts = clean_ts.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 1:
            return float(parts[0])
    except (ValueError, TypeError):
        return 0.0
    return 0.0


def _group_words_into_segments(words: list[dict], max_words: int = 3) -> list[dict]:
    """Groups precise word tokens into snappy 2-4 word kinetic segments with accurate start/end boundaries."""
    if not words:
        return []
    segments = []
    for i in range(0, len(words), max_words):
        chunk = words[i : i + max_words]
        c_start = chunk[0]["start"]
        if i + max_words < len(words):
            c_end = words[i + max_words]["start"]
        else:
            c_end = c_start + (len(chunk) * 0.45)
        # Cap cue duration so subtitle doesn't hang across long natural pauses
        c_end = min(c_end, c_start + max(1.2, len(chunk) * 0.55))
        c_text = " ".join(item["word"] for item in chunk).strip()
        if c_text:
            segments.append({"start": c_start, "end": c_end, "text": c_text})
    return segments


def parse_vtt(subtitle_path: Path) -> list[dict]:
    """Parses VTT files. Handles YouTube's rolling/word-timed format (<timestamp><c> word</c>),
    unescapes HTML entities (&amp;, &#39;, &gt;&gt;), strips speaker markers, and eliminates duplicates.
    """
    text = subtitle_path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\n+", text)
    ts_re = re.compile(
        r"((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})"
    )

    # 1. High-Precision YouTube Karaoke/Word-Timed VTT Parsing
    if "<c>" in text and "</c>" in text:
        raw_words = []
        for b in blocks:
            m = ts_re.search(b)
            if not m:
                continue
            st = _parse_vtt_timestamp(m.group(1))
            et = _parse_vtt_timestamp(m.group(2))
            if et - st < 0.04:
                continue

            for line in b.splitlines():
                if "-->" in line or not line.strip():
                    continue
                if "<c>" in line:
                    clean_line = html.unescape(line)
                    clean_line = re.sub(r">>+", " ", clean_line)
                    parts = re.split(r"<((?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})><c>\s*([^<]+)</c>", clean_line)
                    first_w = re.sub(r"<[^>]+>", "", parts[0]).strip()
                    if first_w:
                        for w in first_w.split():
                            if w:
                                raw_words.append({"start": st, "word": w})
                    for i in range(1, len(parts), 3):
                        if i + 1 < len(parts):
                            t = _parse_vtt_timestamp(parts[i])
                            w = parts[i + 1].strip()
                            if w:
                                raw_words.append({"start": t, "word": w})

        # Deduplicate consecutive identical words/timestamps
        words = []
        for w in raw_words:
            if not words or w["word"] != words[-1]["word"] or abs(w["start"] - words[-1]["start"]) > 0.08:
                words.append(w)

        if words:
            return _group_words_into_segments(words, max_words=3)

    # 2. Standard Cue-Level VTT Parsing (with HTML unescape & rolling deduplication)
    segments = []
    seen_texts = set()
    for b in blocks:
        m = ts_re.search(b)
        if not m:
            continue
        start = _parse_vtt_timestamp(m.group(1))
        end = _parse_vtt_timestamp(m.group(2))
        if end - start < 0.08:
            continue
        lines = [
            l for l in b.splitlines()
            if not ts_re.search(l) and not l.strip().isdigit() and l.strip()
        ]
        raw_text = " ".join(lines)
        clean = html.unescape(raw_text)
        clean = re.sub(r"<[^>]+>", "", clean)
        clean = re.sub(r">>+", " ", clean)
        clean = " ".join(clean.split()).strip()
        if clean and clean not in seen_texts:
            seen_texts.add(clean)
            segments.append({"start": start, "end": end, "text": clean})

    return segments


def transcribe_with_whisper(video_path: Path, model_size: str = "small") -> list[dict]:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(video_path), vad_filter=True, word_timestamps=True)
        raw_words = []
        for seg in segments:
            for w in getattr(seg, "words", []):
                w_text = html.unescape(w.word).strip()
                if w_text:
                    raw_words.append({"start": w.start, "word": w_text})
        if raw_words:
            return _group_words_into_segments(raw_words, max_words=3)
        return [
            {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
            for seg in segments
        ]
    except Exception:
        import whisper
        model = whisper.load_model(model_size)
        result = model.transcribe(str(video_path), word_timestamps=True)
        raw_words = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                w_text = html.unescape(w.get("word", "")).strip()
                if w_text:
                    raw_words.append({"start": w.get("start", seg["start"]), "word": w_text})
        if raw_words:
            return _group_words_into_segments(raw_words, max_words=3)
        return [
            {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
            for seg in result.get("segments", [])
        ]


def get_transcript(video_path: Path | None, subtitle_path: Path | None) -> list[dict]:
    if subtitle_path and subtitle_path.exists():
        segments = parse_vtt(subtitle_path)
        if segments:
            return segments
    if not video_path or not video_path.exists():
        return []
    return transcribe_with_whisper(video_path)
