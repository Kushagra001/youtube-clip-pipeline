"""Automated Publishing Scheduler for YouTube Shorts.

Calculates optimal publication release windows (RFC 3339 format) based on peak
audience engagement hours (lunch & evening unwind), staggering multiple clips
across time slots to prevent algorithmic self-cannibalization.
"""
from datetime import datetime, timedelta, timezone


# 12:00 UTC (lunch US/EU overlap), 17:00 UTC (afternoon peak), 21:00 UTC (evening peak)
DEFAULT_OPTIMAL_HOURS_UTC = [12, 17, 21]
DEFAULT_MIN_LEAD_MINUTES = 45   # Minimum time for YouTube to finish HD processing before public release
DEFAULT_STAGGER_HOURS = 4.0     # Minimum spacing between multiple clips on the same channel


def get_scheduled_publish_time(
    clip_index: int = 0,
    optimal_hours_utc: list[int] | None = None,
    min_lead_minutes: int = DEFAULT_MIN_LEAD_MINUTES,
    stagger_hours: float = DEFAULT_STAGGER_HOURS,
    reference_dt: datetime | None = None,
) -> tuple[str, str, datetime]:
    """Calculates the next optimal ISO-8601 (RFC 3339) timestamp for YouTube publishAt.

    Args:
        clip_index: 0 for the first clip, 1 for the second clip, etc.
        optimal_hours_utc: Target peak hours in UTC (e.g. [12, 17, 21]).
        min_lead_minutes: Minimum minutes from now before a video can be published.
        stagger_hours: Hours to separate multiple clips in the same run.
        reference_dt: Optional base datetime (defaults to current UTC time).

    Returns:
        tuple[str, str, datetime]:
            - iso_timestamp: RFC 3339 string for YouTube API (e.g. "2026-10-23T17:00:00Z")
            - human_display: Friendly display string (e.g. "2026-10-23 17:00 UTC (in 2h 15m)")
            - target_dt: datetime object with UTC timezone
    """
    now = reference_dt or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    slots = sorted(optimal_hours_utc or DEFAULT_OPTIMAL_HOURS_UTC)
    min_allowed = now + timedelta(minutes=min_lead_minutes)

    # 1. Find the earliest optimal slot for clip 0 that meets lead-time requirements
    base_slot = None
    for day_offset in range(4):
        check_date = now.date() + timedelta(days=day_offset)
        for hour in slots:
            slot_dt = datetime(check_date.year, check_date.month, check_date.day, hour, 0, 0, tzinfo=timezone.utc)
            if slot_dt >= min_allowed:
                base_slot = slot_dt
                break
        if base_slot:
            break

    if not base_slot:
        base_slot = min_allowed + timedelta(hours=1)

    # 2. For subsequent clips (clip_index > 0), stagger release
    candidate = base_slot
    if clip_index > 0:
        required_min = base_slot + timedelta(hours=stagger_hours * clip_index)
        staggered_candidate = None
        for day_offset in range(5):
            check_date = required_min.date() + timedelta(days=day_offset)
            for hour in slots:
                slot_dt = datetime(check_date.year, check_date.month, check_date.day, hour, 0, 0, tzinfo=timezone.utc)
                if slot_dt >= required_min:
                    staggered_candidate = slot_dt
                    break
            if staggered_candidate:
                break
        candidate = staggered_candidate or required_min

    # YouTube Data API requires RFC 3339: YYYY-MM-DDTHH:MM:SSZ
    iso_timestamp = candidate.strftime("%Y-%m-%dT%H:%M:%SZ")

    delta = candidate - now
    total_seconds = max(0, int(delta.total_seconds()))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    in_str = f"in {hours}h {minutes}m" if hours > 0 else f"in {minutes}m"
    human_display = f"{candidate.strftime('%Y-%m-%d %H:%M UTC')} ({in_str})"

    return iso_timestamp, human_display, candidate
