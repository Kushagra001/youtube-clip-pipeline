"""Cuts a segment out of the source video and applies a multi-layer digital footprint

transformation (framing, spatial micro-zoom, temporal micro-shift, color grading,
animated progress bar, and YouTube -14 LUFS audio normalization) formatted strictly
as a 9:16 vertical Short (< 60s).
"""
import subprocess
from pathlib import Path

CLIPS_DIR = Path(__file__).resolve().parent.parent / "output" / "clips"


def _normalize_color(color_spec: str | None, default: str = "0xFFCC00@0.98") -> str:
    if not color_spec:
        return default
    c = str(color_spec).strip()
    if c.startswith("#") and len(c) == 7:
        return f"0x{c[1:].upper()}@0.98"
    if c.startswith("0x"):
        return c if "@" in c else f"{c}@0.98"
    return default


def _build_video_filter(
    style: str,
    adjusted_duration: float,
    speed_factor: float = 1.02,
    enable_progress_bar: bool = True,
    meme_theme: str = "dark",
    progress_bar_color: str | None = None,
    framing_info: dict | None = None,
) -> str:
    # 1. Temporal micro-shift (resets PTS to 0 so timeline & progress bar start at t=0)
    pts_scale = f"{1.0 / speed_factor:.6f}"
    pts_filter = f"setpts=PTS-STARTPTS,setpts={pts_scale}*PTS"

    # 2. Color grading & vignette (shifts RGB histograms to break pixel hash)
    color_grade = "eq=contrast=1.06:saturation=1.08:brightness=-0.01:gamma=1.02,vignette=angle=0.22"

    f_info = framing_info or {}
    dom_x = f_info.get("dominant_x_ratio", 0.50)

    if style == "crop":
        # Direct center/face-guided crop to 9:16 with micro-zoom & color grade
        base_filter = (
            f"{pts_filter},"
            f"scale=iw*1.03:-2,{color_grade},"
            f"scale=-2:1920,"
            f"crop=1080:1920:x='max(0,min(iw-1080,iw*{dom_x:.3f}-540))':y=0"
        )
    elif style == "split_screen":
        # Stacked 2-Speaker Split-Screen Layout (Host on top, Guest on bottom)
        card_bg = "0x18181B@0.96" if meme_theme == "dark" else "white@1.0"
        card_border = "0x3F3F46@0.85" if meme_theme == "dark" else "0xE4E4E7@1.0"
        divider_col = _normalize_color(progress_bar_color, default="0x00E5FF@0.95")
        x1 = f_info.get("speaker1_x_ratio", 0.28)
        x2 = f_info.get("speaker2_x_ratio", 0.72)

        base_filter = (
            f"{pts_filter},split=3[bg_in][fg1_in][fg2_in];"
            f"[bg_in]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"gblur=sigma=50,eq=brightness=-0.38:contrast=1.12[bg];"
            f"[fg1_in]scale=iw*1.02:-2,{color_grade},"
            f"crop=w='min(iw,ih*1.15)':h=ih:x='max(0,min(iw-min(iw,ih*1.15),iw*{x1:.3f}-ih*0.575))':y=0,"
            f"scale=1020:640:force_original_aspect_ratio=increase,crop=1020:640,pad=1028:648:4:4:color=white@0.35[panel1];"
            f"[fg2_in]scale=iw*1.02:-2,{color_grade},"
            f"crop=w='min(iw,ih*1.15)':h=ih:x='max(0,min(iw-min(iw,ih*1.15),iw*{x2:.3f}-ih*0.575))':y=0,"
            f"scale=1020:640:force_original_aspect_ratio=increase,crop=1020:640,pad=1028:648:4:4:color=white@0.35[panel2];"
            f"[bg][panel1]overlay=(W-w)/2:340[v_comp1];"
            f"[v_comp1][panel2]overlay=(W-w)/2:1010[v_comp2];"
            f"[v_comp2]drawbox=x=60:y=998:w=960:h=4:color={divider_col}:t=fill,"
            f"drawbox=x=36:y=110:w=1008:h=210:color={card_bg}:t=fill,"
            f"drawbox=x=36:y=110:w=1008:h=210:color={card_border}:t=2"
        )
    elif style == "meme_card":
        # Memezar / 9GAG Viral Meme Template:
        # Dark ambient blurred backdrop, framed centered video player, and top meme header card container
        card_bg = "0x18181B@0.96" if meme_theme == "dark" else "white@1.0"
        card_border = "0x3F3F46@0.85" if meme_theme == "dark" else "0xE4E4E7@1.0"
        pad_border_color = "white@0.25" if meme_theme == "dark" else "white@0.6"

        base_filter = (
            f"{pts_filter},split=2[bg_raw][fg_raw];"
            f"[bg_raw]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"gblur=sigma=50,eq=brightness=-0.38:contrast=1.12[bg];"
            f"[fg_raw]scale=iw*1.03:-2,{color_grade},"
            f"crop=w='min(iw,ih*1.78)':h=ih:x='max(0,min(iw-min(iw,ih*1.78),iw*{dom_x:.3f}-ih*0.89))':y=0,"
            f"scale=1040:-2[card];"
            f"[card]pad=1048:ih+8:4:4:color={pad_border_color}[framed_card];"
            f"[bg][framed_card]overlay=(W-w)/2:(H-h)/2[v_comp];"
            f"[v_comp]drawbox=x=36:y=170:w=1008:h=270:color={card_bg}:t=fill,"
            f"drawbox=x=36:y=170:w=1008:h=270:color={card_border}:t=2"
        )
    else:
        # Editorial Framed Card with blurred, dimmed backdrop
        base_filter = (
            f"{pts_filter},split=2[bg_raw][fg_raw];"
            f"[bg_raw]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"gblur=sigma=45,eq=brightness=-0.12:contrast=1.05[bg];"
            f"[fg_raw]scale=iw*1.03:-2,{color_grade},"
            f"crop=w='min(iw,ih*1.78)':h=ih:x='max(0,min(iw-min(iw,ih*1.78),iw*{dom_x:.3f}-ih*0.89))':y=0,"
            f"scale=1040:-2[card];"
            f"[card]pad=1060:ih+20:10:10:color=white@0.35[framed_card];"
            f"[bg][framed_card]overlay=(W-w)/2:(H-h)/2"
        )

    # 3. Kinetic progress bar with dark track (smoothly animates from 0px to 1080px)
    if enable_progress_bar and adjusted_duration > 0:
        bar_col = _normalize_color(progress_bar_color, default="0xFFCC00@0.98")
        bar_filter = (
            f",drawbox=x=0:y=1906:w=1080:h=10:color=black@0.5:t=fill,"
            f"drawbox=x=0:y=1906:w='min(1080,1080*t/{adjusted_duration:.2f})':"
            f"h=10:color={bar_col}:t=fill"
        )
        return base_filter + bar_filter

    return base_filter


def cut_clip(
    source_video: Path,
    start: float,
    end: float,
    out_name: str,
    vertical_style: str = "meme_card",
    speed_factor: float = 1.02,
    enable_progress_bar: bool = True,
    enable_loudnorm: bool = True,
    meme_theme: str = "dark",
    enable_audio_conditioning: bool = True,
    progress_bar_color: str | None = None,
    enable_smart_framing: bool = True,
    framing_info: dict | None = None,
) -> Path:
    """Cuts and applies digital footprint alteration + smart vertical framing to the clip."""
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLIPS_DIR / f"{out_name}.mp4"
    raw_duration = max(1.0, end - start)
    adjusted_duration = raw_duration / speed_factor

    # Detect speaker framing if enabled and not already provided
    if enable_smart_framing and framing_info is None:
        try:
            from pipeline import framing
            framing_info = framing.detect_speaker_framing(source_video, start_sec=start, end_sec=end)
            if framing_info and framing_info.get("has_faces"):
                print(f"     [Framing] Speaker auto-framing active: dominant_x={framing_info['dominant_x_ratio']}, two_speakers={framing_info['has_two_speakers']}")
        except Exception as fe:
            print(f"     [Framing] Notice: Speaker auto-framing fallback to center ({fe})")
            framing_info = None

    effective_style = vertical_style
    if vertical_style == "auto":
        effective_style = "split_screen" if (framing_info or {}).get("has_two_speakers") else "meme_card"

    vf = _build_video_filter(
        style=effective_style,
        adjusted_duration=adjusted_duration,
        speed_factor=speed_factor,
        enable_progress_bar=enable_progress_bar,
        meme_theme=meme_theme,
        progress_bar_color=progress_bar_color,
        framing_info=framing_info,
    )

    # Audio pipeline: PTS alignment + tempo micro-shift + anti-Content-ID vocal isolation + YouTube -14 LUFS loudness mastering
    af_filters = ["asetpts=PTS-STARTPTS", f"atempo={speed_factor:.2f}"]
    if enable_audio_conditioning:
        af_filters.extend([
            "highpass=f=85",
            "lowpass=f=11500",
            "equalizer=f=3000:t=q:w=1.2:g=2.2",
        ])
    if enable_loudnorm:
        af_filters.append("loudnorm=I=-14:LRA=11:TP=-1.5")
    af = ",".join(af_filters)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(source_video),
        "-t", f"{raw_duration:.3f}",
        "-vf", vf,
        "-af", af,
        "-shortest",
        "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        str(out_path),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return out_path

    # If first pass fails (e.g. loudnorm error on short/unusual audio or strict filters), retry with clean fallback
    err = (res.stderr or "") + " " + (res.stdout or "")
    print(f"  [FFmpeg] Cut encounter note: {err.splitlines()[-1] if err.splitlines() else 'Unknown'}. Retrying with resilient audio...")

    af_fallback = f"asetpts=PTS-STARTPTS,atempo={speed_factor:.2f}"
    cmd_fallback = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(source_video),
        "-t", f"{raw_duration:.3f}",
        "-vf", vf,
        "-af", af_fallback,
        "-shortest",
        "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        str(out_path),
    ]
    res_fb = subprocess.run(cmd_fallback, capture_output=True, text=True)
    if res_fb.returncode != 0:
        err_msg = res_fb.stderr.strip() or res_fb.stdout.strip()
        last_error = "\n".join(err_msg.splitlines()[-8:])
        raise RuntimeError(f"FFmpeg clip cut failed:\n{last_error}")

    return out_path
