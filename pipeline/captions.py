"""Builds a styled .ass subtitle track for a clip (from the slice of the
full transcript that overlaps the clip's time range) and burns it in.
Supports viral meme templates (Memezar / 9GAG style) and standard framing.
"""
import subprocess
from pathlib import Path

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: BurnerHeader,Arial Black,50,&H0000FFFF,&H000000FF,&H00000000,&H90000000,1,0,0,0,100,100,0,0,3,4,0,8,70,70,240,1
Style: MemeHandleDark,Arial,34,&H00D4D4D8,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,7,80,80,205,1
Style: MemeHookDark,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,7,80,80,255,1
Style: MemeHandleLight,Arial,34,&H0052525B,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,7,80,80,205,1
Style: MemeHookLight,Arial,48,&H00000000,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,7,80,80,255,1
Style: Default,Arial Black,64,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,1,0,0,0,100,100,1,0,1,5,3,2,60,60,390,1
Style: TakeawayCardDark,Arial Black,32,&H00FFFFFF,&H000000FF,&H00000000,&HD0141418,1,0,0,0,100,100,0,0,3,3,0,2,60,60,240,1
Style: TakeawayCardLight,Arial Black,32,&H00000000,&H000000FF,&H00000000,&HD0FFFFFF,1,0,0,0,100,100,0,0,3,3,0,2,60,60,240,1
Style: OutroBrandCard,Arial Black,36,&H00FFFFFF,&H000000FF,&H00000000,&HF0121215,1,0,0,0,100,100,0,0,3,4,0,2,80,80,330,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _fmt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _wrap_headline(text: str, max_chars_per_line: int = 34) -> str:
    """Wraps headline text cleanly for ASS subtitles with hard linebreaks (\\N)."""
    words = text.split()
    lines = []
    curr = []
    curr_len = 0
    for w in words:
        item_len = len(w) + (1 if curr else 0)
        if curr_len + item_len <= max_chars_per_line:
            curr.append(w)
            curr_len += item_len
        else:
            if curr:
                lines.append(" ".join(curr))
            curr = [w]
            curr_len = len(w)
    if curr:
        lines.append(" ".join(curr))
    return r"\N".join(lines[:3])


def _format_kinetic_cue(words: list[str]) -> str:
    """Styles a 2-3 word cue in viral Shorts style:
    lead focus word in electric yellow (&H0000FFFF&), remainder in crisp white."""
    if not words:
        return ""
    clean = [w.strip().upper() for w in words if w.strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return rf"{{\c&H0000FFFF&}}{clean[0]}"
    lead = clean[0]
    rest = " ".join(clean[1:])
    return rf"{{\c&H0000FFFF&}}{lead} {{\c&H00FFFFFF&}}{rest}"


def _chunk_segment(seg: dict, max_words: int = 3) -> list[dict]:
    """Splits long segment text into snappy 2-3 word kinetic cues."""
    raw_words = seg["text"].split()
    words = [w for w in raw_words if not (w.startswith("[") and w.endswith("]"))]
    if not words:
        return []
    if len(words) <= max_words:
        return [{
            "start": seg["start"],
            "end": seg["end"],
            "text": _format_kinetic_cue(words),
        }]
    chunks = []
    num_chunks = (len(words) + max_words - 1) // max_words
    dur_per_word = (seg["end"] - seg["start"]) / max(len(words), 1)

    for i in range(num_chunks):
        sub_words = words[i * max_words : (i + 1) * max_words]
        sub_start = seg["start"] + (i * max_words * dur_per_word)
        sub_end = min(seg["end"], sub_start + (len(sub_words) * dur_per_word))
        chunks.append({
            "start": sub_start,
            "end": max(sub_start + 0.1, sub_end),
            "text": _format_kinetic_cue(sub_words),
        })
    return chunks


def build_ass_file(
    clip_segments: list[dict],
    clip_start_offset: float,
    out_path: Path,
    burner_text: str | None = None,
    clip_duration: float | None = None,
    speed_factor: float = 1.0,
    template_style: str = "meme_card",
    meme_theme: str = "dark",
    meme_handle: str = "@viralinsights",
    show_badge: bool = True,
    takeaway_text: str | None = None,
    brand_name: str = "VIRAL INSIGHTS",
    brand_tagline: str = "FOLLOW FOR DAILY INSIGHTS",
    brand_icon: str = "⚡",
    enable_brand_outro: bool = True,
    outro_seconds: float = 1.8,
) -> Path:
    """Builds the complete ASS subtitle track with synchronization, kinetic captions, takeaway outro, and brand card."""
    lines = [ASS_HEADER]
    safe_duration = clip_duration or 60.0
    dur_str = _fmt_ts(safe_duration)
    outro_start_time = max(0.0, safe_duration - outro_seconds) if enable_brand_outro else safe_duration

    # 1. Top Header (Meme Card vs. Burner Header)
    if burner_text:
        clean_burner = burner_text.strip().upper()
        if template_style == "meme_card":
            handle_style = "MemeHandleDark" if meme_theme == "dark" else "MemeHandleLight"
            hook_style = "MemeHookDark" if meme_theme == "dark" else "MemeHookLight"
            wrapped_hook = _wrap_headline(clean_burner, max_chars_per_line=34)

            badge_prefix = r"{\c&H60A5FA&}● {\c}" if show_badge else ""
            lines.append(
                f"Dialogue: 1,0:00:00.00,{dur_str},{handle_style},,0,0,0,,{badge_prefix}{meme_handle}\n"
            )
            lines.append(
                f"Dialogue: 1,0:00:00.00,{dur_str},{hook_style},,0,0,0,,{wrapped_hook}\n"
            )
        else:
            lines.append(
                f"Dialogue: 1,0:00:00.00,{dur_str},BurnerHeader,,0,0,0,,{clean_burner}\n"
            )

    # 2. Fast-paced kinetic subtitles with active yellow word-highlight
    for seg in clip_segments:
        sub_chunks = _chunk_segment(seg, max_words=3)
        for chunk in sub_chunks:
            raw_start = max(0.0, chunk["start"] - clip_start_offset)
            raw_end = max(raw_start + 0.1, chunk["end"] - clip_start_offset)

            # Scale timestamps by speed_factor to preserve perfect speech synchronization
            start = raw_start / speed_factor
            end = min(raw_end / speed_factor, outro_start_time)

            if start >= outro_start_time:
                continue

            text = chunk["text"].replace("\n", " ").strip()
            if not text:
                continue
            lines.append(
                f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Default,,0,0,0,,{text}\n"
            )

    # 3. Transformative Educational Takeaway Outro Banner (final ~3.5s until outro card)
    if takeaway_text and safe_duration >= 6.0:
        takeaway_start = max(0.0, safe_duration - 3.8)
        takeaway_end_str = _fmt_ts(outro_start_time if enable_brand_outro else safe_duration)
        clean_takeaway = takeaway_text.strip().upper()
        takeaway_style = "TakeawayCardDark" if meme_theme == "dark" else "TakeawayCardLight"
        wrapped_takeaway = _wrap_headline(clean_takeaway, max_chars_per_line=38)
        lines.append(
            f"Dialogue: 2,{_fmt_ts(takeaway_start)},{takeaway_end_str},{takeaway_style},,0,0,0,,{{\\c&H00D7FF&}}💡 {{\\c}}{wrapped_takeaway}\n"
        )

    # 4. Center Brand Outro Card (final ~1.8 seconds)
    if enable_brand_outro and safe_duration >= 5.0:
        lines.append(
            f"Dialogue: 3,{_fmt_ts(outro_start_time)},{dur_str},OutroBrandCard,,0,0,0,,{{\\fad(200,0)}}{{\\fs66\\c&H00D7FF&}}{brand_icon}{{\\c&HFFFFFF&}}\\N\\N{{\\fs42\\b1}}{brand_name}\\N{{\\fs24\\b0\\c&H00D4D4D8&}}{brand_tagline}\n"
        )

    out_path.write_text("".join(lines), encoding="utf-8")
    return out_path


def segments_in_range(
    transcript: list[dict], start: float, end: float
) -> list[dict]:
    return [
        s for s in transcript
        if s["end"] > start and s["start"] < end
    ]


def burn_in_captions(video_path: Path, ass_path: Path, out_path: Path) -> Path:
    # Escape colons and backslashes for cross-platform FFmpeg filter syntax
    ass_escaped = ass_path.resolve().as_posix().replace(":", "\\:")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass=filename='{ass_escaped}'",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "copy",
            str(out_path),
        ],
        check=True,
    )
    return out_path
