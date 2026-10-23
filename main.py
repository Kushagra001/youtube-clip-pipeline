"""Orchestrates the full pipeline:
discovery -> download -> transcript -> highlights -> clip -> caption -> (optionally) upload,
for viral videos discovered or listed in config/sources.yaml.
"""
import sys
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load local .env if present
load_dotenv()

# Ensure UTF-8 output across Windows and Linux terminals
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pipeline import (
    discovery,
    download,
    transcript as transcript_mod,
    highlights,
    clip,
    captions,
    state as state_mod,
    notifications,
    scheduler,
    export_platforms,
)

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "sources.yaml"
CHANNELS_DIR = Path(__file__).resolve().parent / "config" / "channels"


def load_config(config_path: Path | None = None) -> dict:
    target_path = config_path or CONFIG_PATH
    with open(target_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_channel_config(channel_query: str) -> Path | None:
    if not CHANNELS_DIR.exists():
        return None
    for p in sorted(CHANNELS_DIR.glob("*.yaml")):
        if p.stem == channel_query or p.stem.startswith(channel_query) or channel_query.lower() in p.stem.lower():
            return p
    return None


def process_video(item: dict | str, cfg: dict, st: dict, channel_id: str | None = None) -> None:
    if isinstance(item, str):
        url = item
        video_id = download.get_video_id(url)
        title = None
    else:
        url = item["url"]
        video_id = item.get("video_id") or download.get_video_id(url)
        title = item.get("title")

    print(f"\n=== Processing: {url} ===")
    print(f"  Video ID: {video_id}")

    # Check processed state BEFORE downloading video
    if state_mod.is_processed(st, video_id):
        print(f"  Already processed in previous run, skipping: {video_id}")
        return

    targeted = cfg.get("targeted_download", True)
    full_video_path = None
    tx = []

    if targeted:
        print("  Extracting subtitles (targeted mode)...")
        try:
            sub_path = download.download_subtitles(url, video_id=video_id)
            if sub_path and sub_path.exists():
                tx = transcript_mod.get_transcript(None, sub_path)
                if tx:
                    print(f"  Transcript: {len(tx)} segments (from online captions)")
        except Exception as sub_err:
            print(f"  [Transcript] Online subtitle check note: {sub_err}")

        if not tx:
            print("  No online captions available; downloading source video for Whisper transcription...")
            try:
                info = download.download_video(url, video_id=video_id, title=title)
                full_video_path = info["video_path"]
                tx = transcript_mod.get_transcript(full_video_path, info["subtitle_path"])
                print(f"  Transcript: {len(tx)} segments (via Whisper)")
            except Exception as dl_err:
                print(f"  [Transcript] Source video download/transcription failed: {dl_err}")
                return
    else:
        info = download.download_video(url, video_id=video_id, title=title)
        full_video_path = info["video_path"]
        tx = transcript_mod.get_transcript(full_video_path, info["subtitle_path"])
        print(f"  Transcript: {len(tx)} segments")

    if not tx:
        print(f"  No dialogue or transcript could be extracted for video {video_id}. Marking processed.")
        state_mod.mark_processed(st, video_id)
        state_mod.save_state(st, channel_id=channel_id)
        return

    # Select highlights (strictly tuned for YouTube Shorts < 60s)
    picks = highlights.find_highlights(
        tx,
        max_clips=cfg.get("max_clips_per_video", 3),
        min_seconds=cfg.get("min_clip_seconds", 25),
        max_seconds=cfg.get("max_clip_seconds", 55),
        method=cfg.get("highlight_method", "heuristic"),
        source_title=title,
    )
    print(f"  Highlights found: {len(picks)}")

    if not picks:
        print("  No suitable highlight segments found for this video.")
        state_mod.mark_processed(st, video_id)
        state_mod.save_state(st, channel_id=channel_id)
        return

    speed_factor = cfg.get("speed_microshift", 1.02)
    enable_burner = cfg.get("burner_text", True)
    enable_progress_bar = cfg.get("progress_bar", True)
    enable_loudnorm = cfg.get("audio_loudnorm", True)
    progress_bar_color = cfg.get("progress_bar_color") or cfg.get("branding", {}).get("progress_bar_color")

    fair_use_cfg = cfg.get("fair_use", {})
    enable_takeaway = fair_use_cfg.get("enable_takeaway_outro", True)
    enable_audio_cond = fair_use_cfg.get("audio_conditioning", True)

    branding_cfg = cfg.get("branding", {})
    brand_name = branding_cfg.get("channel_name", "VIRAL INSIGHTS")
    brand_tagline = branding_cfg.get("tagline", "FOLLOW FOR DAILY INSIGHTS")
    brand_icon = branding_cfg.get("icon", "⚡")
    enable_brand_outro = branding_cfg.get("enabled", True)
    outro_seconds = branding_cfg.get("outro_seconds", 1.8)

    clips_succeeded = 0

    # Cut clips, apply framing & digital footprint shift, and burn in captions
    for i, pick in enumerate(picks):
        clip_name = f"{video_id}_clip{i+1}"
        raw_duration = max(1.0, pick["end"] - pick["start"])
        adjusted_duration = raw_duration / speed_factor
        print(f"  -> Clip {i+1}: {pick['title']} [{pick['start']:.1f}-{pick['end']:.1f}] ({adjusted_duration:.1f}s)")
        if enable_burner and pick.get("burner_text"):
            print(f"     Burner Headline: '{pick['burner_text']}'")
        if enable_takeaway and pick.get("takeaway"):
            print(f"     Educational Takeaway: '{pick['takeaway']}'")

        vertical_style = cfg.get("vertical_style", "meme_card")
        meme_cfg = cfg.get("meme_template", {})
        meme_theme = meme_cfg.get("theme", "dark")
        meme_handle = meme_cfg.get("handle", "@viralinsights")
        show_badge = meme_cfg.get("badge", True)

        try:
            # Download targeted clip section if full video wasn't downloaded
            if full_video_path and full_video_path.exists():
                source_cut_file = full_video_path
                cut_start = pick["start"]
                cut_end = pick["end"]
            else:
                print(f"     Downloading targeted section [{pick['start']:.1f}s - {pick['end']:.1f}s]...")
                source_cut_file, cut_start, cut_end = download.download_clip_section(
                    url, video_id, pick["start"], pick["end"], out_name=f"{video_id}_raw_{i+1}"
                )

            # Detect speaker framing for intelligent centering and split-screen
            framing_info = None
            if cfg.get("smart_speaker_framing", True):
                try:
                    from pipeline import framing
                    framing_info = framing.detect_speaker_framing(source_cut_file, start_sec=cut_start, end_sec=cut_end)
                    if framing_info and framing_info.get("has_faces"):
                        print(f"     [Framing] Speaker auto-framing active: dominant_x={framing_info['dominant_x_ratio']}, two_speakers={framing_info['has_two_speakers']}")
                except Exception as fe:
                    print(f"     [Framing] Speaker auto-framing fallback to center ({fe})")

            resolved_style = vertical_style
            if vertical_style == "auto":
                resolved_style = "split_screen" if (framing_info or {}).get("has_two_speakers") else "meme_card"
                print(f"     [Framing] Dynamic layout selected: '{resolved_style}'")

            raw_clip_path = clip.cut_clip(
                source_cut_file,
                cut_start,
                cut_end,
                clip_name,
                vertical_style=resolved_style,
                speed_factor=speed_factor,
                enable_progress_bar=enable_progress_bar,
                enable_loudnorm=enable_loudnorm,
                meme_theme=meme_theme,
                enable_audio_conditioning=enable_audio_cond,
                progress_bar_color=progress_bar_color,
                enable_smart_framing=cfg.get("smart_speaker_framing", True),
                framing_info=framing_info,
            )

            clip_segments = captions.segments_in_range(tx, pick["start"], pick["end"])
            ass_path = raw_clip_path.with_suffix(".ass")
            captions.build_ass_file(
                clip_segments,
                pick["start"],
                ass_path,
                burner_text=pick.get("burner_text") if enable_burner else None,
                clip_duration=adjusted_duration,
                speed_factor=speed_factor,
                template_style=resolved_style,
                meme_theme=meme_theme,
                meme_handle=meme_handle,
                show_badge=show_badge,
                takeaway_text=pick.get("takeaway") if enable_takeaway else None,
                brand_name=brand_name,
                brand_tagline=brand_tagline,
                brand_icon=brand_icon,
                enable_brand_outro=enable_brand_outro,
                outro_seconds=outro_seconds,
            )

            # Resolve channel logo if configured or available in assets
            logo_setting = branding_cfg.get("logo_path")
            logo_path = None
            if logo_setting:
                p = Path(logo_setting)
                if not p.is_absolute():
                    p = Path(__file__).resolve().parent / p
                if p.exists():
                    logo_path = p

            if not logo_path:
                ch_id = cfg.get("channel_id")
                if ch_id:
                    fallback_logo = Path(__file__).resolve().parent / "assets" / "logos" / f"{ch_id}.png"
                    if fallback_logo.exists():
                        logo_path = fallback_logo

            outro_start = max(0.0, adjusted_duration - outro_seconds) if enable_brand_outro else 0.0

            captioned_path = raw_clip_path.with_name(f"{clip_name}_captioned.mp4")
            captions.burn_in_captions(
                raw_clip_path,
                ass_path,
                captioned_path,
                logo_path=logo_path if enable_brand_outro else None,
                outro_start=outro_start,
                duration=adjusted_duration,
            )

            # Multi-Platform Packaging (TikTok, Instagram Reels, YouTube Shorts)
            if cfg.get("multiplatform_export", True):
                try:
                    export_platforms.export_multiplatform_bundle(
                        captioned_video_path=captioned_path,
                        channel_id=channel_id or "default",
                        video_id=video_id,
                        clip_index=i,
                        pick=pick,
                        cfg=cfg,
                        duration_sec=adjusted_duration,
                        source_url=url,
                        source_channel=item.get("channel") if isinstance(item, dict) else None,
                    )
                except Exception as exp_err:
                    print(f"     [Export Error] Multi-platform packaging notice: {exp_err}")

            if cfg.get("auto_upload", False):
                yt_cfg = cfg.get("youtube", {})
                max_daily = yt_cfg.get("max_uploads_per_day", 2)

                if not state_mod.can_upload(st, max_uploads_per_day=max_daily):
                    print(f"     [YouTube Upload] Daily upload limit ({max_daily}) reached. Skipping upload to protect API quota & anti-spam status.")
                    print(f"     Saved locally: {captioned_path}")
                else:
                    from pipeline import upload_youtube
                    short_title = pick["title"][:50]
                    if "#shorts" not in short_title.lower():
                        short_title += " #shorts"

                    channel_name = item.get("channel") if isinstance(item, dict) else "Original Creator"
                    start_mins = int(pick["start"] // 60)
                    start_secs = int(pick["start"] % 60)
                    timestamp_str = f"{start_mins}:{start_secs:02d}"

                    takeaway_line = f"💡 {pick.get('takeaway', '')}\n\n" if pick.get("takeaway") else ""
                    disc_cfg = cfg.get("discovery", {})
                    raw_tags = disc_cfg.get("scrape_hashtags", [])
                    clean_tags = [t.lstrip("#").strip() for t in raw_tags if t.strip()]
                    hashtags_str = " ".join([f"#{t}" for t in clean_tags]) if clean_tags else "#shorts #viral"
                    if "#shorts" not in hashtags_str.lower():
                        hashtags_str += " #shorts"

                    description = (
                        f"{pick.get('burner_text', '')}\n\n"
                        f"{pick['hook']}\n\n"
                        f"{takeaway_line}"
                        f"---\n"
                        f"Transformative analysis & educational commentary under Fair Use (17 U.S.C. § 107).\n"
                        f"Creator Attribution: {channel_name}\n"
                        f"Original Source: {url} (Segment ~{timestamp_str})\n\n"
                        f"{hashtags_str}"
                    )

                    configured_privacy = yt_cfg.get("privacy_status", "private").lower()
                    schedule_cfg = yt_cfg.get("publish_schedule", {})
                    schedule_enabled = (configured_privacy == "scheduled") or schedule_cfg.get("enabled", False)

                    publish_at_iso = None
                    sched_display = None
                    if schedule_enabled:
                        publish_at_iso, sched_display, _ = scheduler.get_scheduled_publish_time(
                            clip_index=i,
                            optimal_hours_utc=schedule_cfg.get("optimal_hours_utc"),
                            min_lead_minutes=schedule_cfg.get("min_lead_time_minutes", 45),
                            stagger_hours=schedule_cfg.get("stagger_hours", 4.0),
                        )
                        print(f"     [Scheduler] Peak engagement scheduled release: {sched_display}")

                    upload_tags = clean_tags + ["shorts", "viral"]
                    video_id_uploaded = upload_youtube.upload_short(
                        str(captioned_path),
                        title=short_title,
                        description=description,
                        privacy_status=configured_privacy,
                        category_id=yt_cfg.get("category_id", "24"),
                        tags=upload_tags,
                        token_env_var=yt_cfg.get("token_env_var"),
                        made_for_kids=yt_cfg.get("made_for_kids", False),
                        publish_at=publish_at_iso,
                    )
                    if video_id_uploaded:
                        state_mod.record_upload(st)
                        state_mod.record_uploaded_short(
                            st,
                            video_id=video_id_uploaded,
                            source_video_id=video_id,
                            title=short_title,
                            creator=channel_name,
                            topic=cfg.get("discovery", {}).get("niche_desc", ""),
                            tags=upload_tags,
                            privacy_status="scheduled" if publish_at_iso else configured_privacy,
                            scheduled_at=sched_display if publish_at_iso else None,
                        )
                        print(f"     Uploaded: https://youtube.com/watch?v={video_id_uploaded}")
                        notifications.notify_upload_success(
                            channel_name=brand_name,
                            handle=meme_handle,
                            title=short_title,
                            video_id=video_id_uploaded,
                            duration_sec=adjusted_duration,
                            source_channel=channel_name,
                            tags=upload_tags,
                            privacy_status="scheduled" if publish_at_iso else configured_privacy,
                            scheduled_at=sched_display if publish_at_iso else None,
                        )
                    else:
                        print(f"     Upload failed or skipped. Clip saved locally: {captioned_path}")
                        notifications.notify_upload_failure(
                            channel_name=brand_name,
                            handle=meme_handle,
                            title=short_title,
                            error_msg="YouTube Data API upload returned None or authentication failed.",
                            url=url,
                        )
            else:
                print(f"     Saved locally: {captioned_path}")

            clips_succeeded += 1
        except Exception as clip_err:
            print(f"     [Clip Error] Error processing Clip {i+1} ({pick.get('title')}): {clip_err}", file=sys.stderr)
            continue

    # Clean up intermediate slice files to conserve runner disk space
    download.cleanup_intermediate_files(f"{video_id}_raw")

    state_mod.mark_processed(st, video_id)
    state_mod.save_state(st, channel_id=channel_id)


def run_channel_pipeline(config_path: Path, channel_id: str | None = None) -> None:
    cfg = load_config(config_path)
    cid = channel_id or cfg.get("channel_id")
    st = state_mod.load_state(cid)

    ch_name = cfg.get("branding", {}).get("channel_name", cid or "Default")
    print(f"\n=================================================================")
    print(f" 🚀 Running Pipeline for Channel: {ch_name} (ID: {cid or 'default'})")
    print(f" Config: {config_path.name}")
    print(f"=================================================================")

    # 0. Sync channel retention analytics to update algorithmic self-tuning discovery weights
    try:
        from pipeline import analytics
        if st.get("uploaded_shorts"):
            print(f"  [Analytics] Checking retention performance for {len(st['uploaded_shorts'])} previously uploaded Shorts...")
            analytics.sync_channel_analytics(cid, st)
    except Exception as a_err:
        print(f"  [Analytics] Analytics sync note: {a_err}")

    # 1. Autonomous discovery of viral creators and videos
    discovered_videos = discovery.discover_and_select_videos(cfg, st)

    # 2. Any explicit manual video entries from config
    manual_entries = cfg.get("videos", []) or []
    candidate_items = list(discovered_videos)

    for entry in manual_entries:
        if isinstance(entry, dict) and entry.get("url") and "REPLACE_ME" not in entry["url"]:
            candidate_items.append(entry)
        elif isinstance(entry, str) and "REPLACE_ME" not in entry:
            candidate_items.append({"url": entry})

    if not candidate_items:
        print(f"\nNo candidate viral videos to process for {ch_name}. Check channel settings.")
        return True

    print(f"\n=== Total videos queued for {ch_name}: {len(candidate_items)} ===")
    success_count = 0
    error_count = 0

    for item in candidate_items:
        url = item["url"] if isinstance(item, dict) else item
        try:
            process_video(item, cfg, st, channel_id=cid)
            success_count += 1
        except Exception as e:
            error_count += 1
            print(f"  ERROR processing {url}: {e}", file=sys.stderr)
            b_name = cfg.get("branding", {}).get("channel_name", cid or "Default")
            m_handle = cfg.get("meme_template", {}).get("handle", "@channel")
            target_title = item.get("title", url) if isinstance(item, dict) else url
            notifications.notify_upload_failure(
                channel_name=b_name,
                handle=m_handle,
                title=str(target_title),
                error_msg=str(e),
                url=url,
            )
            continue

    if error_count > 0 and success_count == 0:
        print(f"\n❌ [Channel Failure] All candidate videos ({error_count}/{len(candidate_items)}) failed for {ch_name}!", file=sys.stderr)
        return False

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="YouTube Clipping Pipeline")
    parser.add_argument(
        "--channel",
        type=str,
        default="",
        help="Channel profile to run (e.g. acc_01, acc_02_dogs, 'all', or omit for default config)",
    )
    parser.add_argument(
        "--analytics",
        action="store_true",
        help="Display performance analytics dashboard for channel(s)",
    )
    parser.add_argument(
        "--force-sync",
        action="store_true",
        help="Force fresh stats extraction from YouTube for analytics",
    )
    args = parser.parse_args()

    # Analytics Dashboard Display Mode
    if args.analytics:
        from pipeline import analytics
        if not args.channel or args.channel.lower() == "all":
            channel_files = sorted(CHANNELS_DIR.glob("*.yaml")) if CHANNELS_DIR.exists() else []
            found_any = False
            for ch_file in channel_files:
                c_id = ch_file.stem
                st = state_mod.load_state(c_id)
                if st.get("uploaded_shorts"):
                    analytics.sync_channel_analytics(c_id, st, force=args.force_sync)
                    print(analytics.render_analytics_dashboard(c_id, st))
                    found_any = True
            if not found_any:
                print("No uploaded Shorts recorded across channels yet. State will populate upon successful uploads.")
            return
        else:
            matched = find_channel_config(args.channel)
            c_id = matched.stem if matched else args.channel
            st = state_mod.load_state(c_id)
            analytics.sync_channel_analytics(c_id, st, force=args.force_sync)
            print(analytics.render_analytics_dashboard(c_id, st))
            return

    if not args.channel:
        # Default run with sources.yaml
        ok = run_channel_pipeline(CONFIG_PATH, channel_id="default")
        if not ok:
            sys.exit(1)
        return

    if args.channel.lower() == "all":
        channel_files = sorted(CHANNELS_DIR.glob("*.yaml")) if CHANNELS_DIR.exists() else []
        if not channel_files:
            print("No channel configs found in config/channels/")
            return
        print(f"\n=== Found {len(channel_files)} channels. Running sequentially... ===")
        all_ok = True
        for ch_file in channel_files:
            ch_ok = run_channel_pipeline(ch_file, channel_id=ch_file.stem)
            if not ch_ok:
                all_ok = False
        if not all_ok:
            sys.exit(1)
        return

    # Specific channel lookup
    matched_config = find_channel_config(args.channel)
    if not matched_config:
        print(f"ERROR: Could not find channel configuration matching '{args.channel}' in config/channels/")
        print("Available channels:")
        for p in sorted(CHANNELS_DIR.glob("*.yaml")):
            print(f"  - {p.stem}")
        sys.exit(1)

    ok = run_channel_pipeline(matched_config, channel_id=matched_config.stem)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
