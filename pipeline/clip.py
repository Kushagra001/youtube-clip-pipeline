"""Cuts a segment out of the source video and applies a multi-layer digital footprint

transformation (framing, spatial micro-zoom, temporal micro-shift, color grading,
animated progress bar, and YouTube -14 LUFS audio normalization) formatted strictly
as a 9:16 vertical Short (< 60s).
"""
import subprocess
from pathlib import Path

CLIPS_DIR = Path(__file__).resolve().parent.parent / "output" / "clips"


def _build_video_filter(
    style: str,
    adjusted_duration: float,
    speed_factor: float = 1.02,
    enable_progress_bar: bool = True,
    meme_theme: str = "dark",
) -> str:
    # 1. Temporal micro-shift (resets PTS to 0 so timeline & progress bar start at t=0)
    pts_scale = f"{1.0 / speed_factor:.6f}"
    pts_filter = f"setpts=PTS-STARTPTS,setpts={pts_scale}*PTS"

    # 2. Color grading & vignette (shifts RGB histograms to break pixel hash)
    color_grade = "eq=contrast=1.06:saturation=1.08:brightness=-0.01:gamma=1.02,vignette=angle=0.22"

    if style == "crop":
        # Direct center-crop to 9:16 with micro-zoom & color grade
        base_filter = (
            f"{pts_filter},"
            f"scale=iw*1.03:-2,{color_grade},"
            f"scale=-2:1920,crop=1080:1920"
        )
    elif style == "meme_card":
        # Memezar / 9GAG Viral Meme Template:
        # Dark ambient blurred backdrop, framed centered video player, and top meme header card container
        card_bg = "0x18181B@0.96" if meme_theme == "dark" else "white@0.98"
        card_border = "0x3F3F46@0.85" if meme_theme == "dark" else "0xD4D4D8@0.9"

        base_filter = (
            f"{pts_filter},split=2[bg_raw][fg_raw];"
            f"[bg_raw]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"gblur=sigma=50,eq=brightness=-0.38:contrast=1.12[bg];"
            f"[fg_raw]scale=iw*1.03:-2,{color_grade},scale=1040:-2[card];"
            f"[card]pad=1048:ih+8:4:4:color=white@0.25[framed_card];"
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
            f"[fg_raw]scale=iw*1.03:-2,{color_grade},scale=1040:-2[card];"
            f"[card]pad=1060:ih+20:10:10:color=white@0.35[framed_card];"
            f"[bg][framed_card]overlay=(W-w)/2:(H-h)/2"
        )

    # 3. Kinetic progress bar with dark track (smoothly animates from 0px to 1080px)
    if enable_progress_bar and adjusted_duration > 0:
        bar_filter = (
            f",drawbox=x=0:y=1906:w=1080:h=10:color=black@0.5:t=fill,"
            f"drawbox=x=0:y=1906:w='min(1080,1080*t/{adjusted_duration:.2f})':"
            f"h=10:color=0xFFCC00@0.98:t=fill"
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
) -> Path:
    """Cuts and applies digital footprint alteration + vertical framing to the clip."""
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLIPS_DIR / f"{out_name}.mp4"
    raw_duration = max(1.0, end - start)
    adjusted_duration = raw_duration / speed_factor

    vf = _build_video_filter(
        style=vertical_style,
        adjusted_duration=adjusted_duration,
        speed_factor=speed_factor,
        enable_progress_bar=enable_progress_bar,
        meme_theme=meme_theme,
    )

    # Audio pipeline: tempo micro-shift + anti-Content-ID vocal isolation + YouTube -14 LUFS loudness mastering
    af_filters = [f"atempo={speed_factor:.2f}"]
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
        "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        str(out_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        # If loudnorm fails on peculiar audio streams, retry with basic filters
        if enable_loudnorm:
            af_fb_filters = [f"atempo={speed_factor:.2f}"]
            if enable_audio_conditioning:
                af_fb_filters.append("highpass=f=85")
            af_fallback = ",".join(af_fb_filters)
            cmd_fallback = [
                "ffmpeg", "-y",
                "-ss", f"{start:.3f}",
                "-i", str(source_video),
                "-t", f"{raw_duration:.3f}",
                "-vf", vf,
                "-af", af_fallback,
                "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "160k",
                str(out_path),
            ]
            subprocess.run(cmd_fallback, check=True)
        else:
            raise e

    return out_path
