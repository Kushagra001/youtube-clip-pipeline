"""Produces a timestamped transcript: [{start, end, text}, ...]

Prefers YouTube's own captions (fast, free). Falls back to local
transcription with faster-whisper (CPU) when no captions exist —
this is the slow path, so it's worth checking sources have captions
where possible.
"""
import re
from pathlib import Path


def _parse_vtt_timestamp(ts: str) -> float:
    # 00:01:23.456 -> seconds
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_vtt(subtitle_path: Path) -> list[dict]:
    text = subtitle_path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\n+", text)
    segments = []
    ts_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
    )
    for block in blocks:
        m = ts_re.search(block)
        if not m:
            continue
        start, end = _parse_vtt_timestamp(m.group(1)), _parse_vtt_timestamp(m.group(2))
        lines = block.split("\n")
        # drop the timestamp line and any cue-settings/index lines
        content_lines = [
            l for l in lines
            if not ts_re.search(l) and not l.strip().isdigit() and l.strip()
        ]
        content = " ".join(content_lines).strip()
        # strip inline vtt tags like <00:00:01.000><c> word</c>
        content = re.sub(r"<[^>]+>", "", content).strip()
        if content:
            segments.append({"start": start, "end": end, "text": content})
    return _dedupe_rolling_captions(segments)


def _dedupe_rolling_captions(segments: list[dict]) -> list[dict]:
    """Auto-captions often repeat overlapping text across cues; collapse
    consecutive near-duplicate lines so downstream LLM calls aren't fed
    heavily redundant transcript."""
    cleaned = []
    for seg in segments:
        if cleaned and seg["text"] == cleaned[-1]["text"]:
            cleaned[-1]["end"] = seg["end"]
            continue
        cleaned.append(seg)
    return cleaned


def transcribe_with_whisper(video_path: Path, model_size: str = "small") -> list[dict]:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(video_path), vad_filter=True)
        return [
            {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
            for seg in segments
        ]
    except ImportError:
        import whisper
        model = whisper.load_model(model_size)
        result = model.transcribe(str(video_path))
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
        raise FileNotFoundError(f"Cannot transcribe: no subtitle found and video file not available at {video_path}")
    # No usable captions — fall back to local transcription.
    return transcribe_with_whisper(video_path)
