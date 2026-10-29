"""Uploads a finished clip to YouTube as a Short, using a pre-generated
OAuth refresh token (see pipeline/get_youtube_token.py for one-time setup).
"""
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials

load_dotenv()
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _resolve_credentials_for_channel(token_env_var: str | None = None, channel_config: dict | None = None) -> tuple[str | None, str | None]:
    """Resolves (client_id, client_secret) dynamically across Project 1, 2, and 3:
    - P1: acc_01 .. acc_03 (YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET)
    - P2: acc_04 .. acc_06 (YOUTUBE_CLIENT_ID_P2 / YOUTUBE_CLIENT_SECRET_P2)
    - P3: acc_07 .. acc_10 (YOUTUBE_CLIENT_ID_P3 / YOUTUBE_CLIENT_SECRET_P3)
    """
    ch_id = ""
    if channel_config:
        ch_id = channel_config.get("channel_id") or channel_config.get("channel_name", "")
    ch_ref = f"{ch_id} {token_env_var or ''}".lower()

    # Check Project 2
    if any(k in ch_ref for k in ["acc_04", "acc_05", "acc_06", "acc_4", "acc_5", "acc_6", "motivation", "finance", "business"]):
        cid = os.environ.get("YOUTUBE_CLIENT_ID_P2")
        sec = os.environ.get("YOUTUBE_CLIENT_SECRET_P2")
        if cid and sec:
            return cid, sec

    # Check Project 3
    if any(k in ch_ref for k in ["acc_07", "acc_08", "acc_09", "acc_10", "acc_7", "acc_8", "acc_9", "food", "ai_tools", "grooming", "mental_health"]):
        cid = os.environ.get("YOUTUBE_CLIENT_ID_P3")
        sec = os.environ.get("YOUTUBE_CLIENT_SECRET_P3")
        if cid and sec:
            return cid, sec

    # Default: Project 1 (or fallback)
    cid = os.environ.get("YOUTUBE_CLIENT_ID_P1") or os.environ.get("YOUTUBE_CLIENT_ID")
    sec = os.environ.get("YOUTUBE_CLIENT_SECRET_P1") or os.environ.get("YOUTUBE_CLIENT_SECRET")
    return cid, sec


def _get_service(token_env_var: str | None = None, channel_config: dict | None = None):
    refresh_token = None
    if token_env_var:
        refresh_token = os.environ.get(token_env_var)
    if not refresh_token:
        refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    # Fallback: check per-channel tokens if default YOUTUBE_REFRESH_TOKEN is unset
    if not refresh_token:
        for i in range(1, 11):
            cand = os.environ.get(f"YOUTUBE_REFRESH_TOKEN_ACC_{i:02d}")
            if cand:
                refresh_token = cand
                break

    if not refresh_token:
        var_name = token_env_var or "YOUTUBE_REFRESH_TOKEN"
        raise ValueError(f"Missing YouTube refresh token in environment variable: {var_name}")

    client_id, client_secret = _resolve_credentials_for_channel(token_env_var, channel_config)
    if not client_id or not client_secret:
        raise ValueError("Missing YouTube OAuth client credentials in environment (check YOUTUBE_CLIENT_ID / P2 / P3)")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds)


def validate_video_file(video_path: str) -> tuple[bool, str]:
    """Validates video stream integrity, duration, and tracks before sending to YouTube."""
    import json
    import subprocess
    from pathlib import Path

    p = Path(video_path)
    if not p.exists() or p.stat().st_size < 50 * 1024:
        return False, f"File missing or truncated (<50KB): {p.stat().st_size if p.exists() else 0} bytes"

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration,size:stream=codec_type,codec_name,sample_aspect_ratio,width,height",
            "-of", "json",
            str(p)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return False, f"FFprobe integrity check failed: {res.stderr.strip()[:150]}"
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        has_video = any(s.get("codec_type") == "video" for s in streams)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        if not has_video:
            return False, "Video stream missing in MP4 container"
        if not has_audio:
            return False, "Audio stream missing in MP4 container"

        dur = float(data.get("format", {}).get("duration", 0))
        if dur > 58.0:
            return False, f"Duration {dur:.1f}s exceeds safe Shorts ceiling (58.0s)"
        if dur < 8.0:
            return False, f"Duration {dur:.1f}s too short (<8.0s)"
        return True, "OK"
    except Exception as e:
        return True, f"Validation bypassed: {e}"


_LAST_UPLOAD_ERROR = None


def get_last_upload_error() -> str:
    """Returns the exact reason why the last YouTube upload failed."""
    global _LAST_UPLOAD_ERROR
    return _LAST_UPLOAD_ERROR or "YouTube Data API upload returned None or authentication failed."


def upload_short(
    video_path: str,
    title: str,
    description: str,
    privacy_status: str = "private",
    category_id: str = "24",
    tags: list[str] | None = None,
    token_env_var: str | None = None,
    made_for_kids: bool = False,
    publish_at: str | None = None,
) -> str | None:
    """Uploads a vertical Short to YouTube with resumable chunking, quota error protection, and scheduled release support."""
    global _LAST_UPLOAD_ERROR
    _LAST_UPLOAD_ERROR = None
    from googleapiclient.errors import HttpError
    from pathlib import Path

    v_file = Path(video_path)
    if not v_file.exists() or v_file.stat().st_size == 0:
        _LAST_UPLOAD_ERROR = f"Video file does not exist or is empty at {video_path}"
        print(f"  [YouTube Upload] Error: {_LAST_UPLOAD_ERROR}")
        return None

    is_valid, reason = validate_video_file(video_path)
    if not is_valid:
        _LAST_UPLOAD_ERROR = f"Pre-flight check failed: {reason}"
        print(f"  [YouTube Upload] {_LAST_UPLOAD_ERROR}. Aborting upload to prevent processing abandonment.")
        return None

    try:
        youtube = _get_service(token_env_var=token_env_var, channel_config=channel_config)
    except Exception as e:
        err_msg = str(e)
        if "invalid_grant" in err_msg:
            _LAST_UPLOAD_ERROR = "OAuth token expired or revoked (invalid_grant). In Google Cloud Console, switch Publishing status from 'Testing' to 'In Production' and regenerate token."
        else:
            _LAST_UPLOAD_ERROR = f"Authentication setup error: {e}"
        print(f"  [YouTube Upload] {_LAST_UPLOAD_ERROR}")
        return None

    # YouTube rejects video titles containing '<' or '>' characters (HTTP 400 invalidTitle)
    clean_title = title.replace("<", "").replace(">", "").strip()[:100]
    import re
    clean_title = re.sub(r"\.\.\.\s*(#shorts)", r" \1", clean_title, flags=re.IGNORECASE)
    clean_title = re.sub(r"[,;:\-]\s*(#shorts)", r" \1", clean_title, flags=re.IGNORECASE)
    clean_desc = description[:4990]

    # Per YouTube API specification: publishAt requires privacyStatus to be "private"
    effective_privacy = "private" if publish_at else privacy_status
    status_dict = {
        "privacyStatus": effective_privacy,
        "selfDeclaredMadeForKids": made_for_kids,
        "embeddable": True,
    }
    if publish_at:
        status_dict["publishAt"] = publish_at
        print(f"  [YouTube Upload] Scheduled release configured: {publish_at} (status: private until release)")

    body = {
        "snippet": {
            "title": clean_title,
            "description": clean_desc,
            "categoryId": str(category_id),
            "tags": tags or ["#shorts", "shorts", "viral", "podcast", "clips"],
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": status_dict,
    }

    try:
        import time
        # Standardize chunk size to 4MB (multiple of 256KB) for robust resumable streaming
        media = MediaFileUpload(
            video_path,
            chunksize=4 * 1024 * 1024,
            resumable=True,
            mimetype="video/mp4",
        )
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        retry_count = 0
        max_retries = 5

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    print(f"  [YouTube Upload] Progress: {pct}%")
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504]:
                    retry_count += 1
                    if retry_count > max_retries:
                        raise e
                    sleep_time = min(30, 2 ** retry_count)
                    print(f"  [YouTube Upload] Server status {e.resp.status}. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    raise e
            except (ConnectionError, TimeoutError, OSError) as e:
                # Differentiate between non-retryable bugs and retryable transient network/socket/SSL issues
                retry_count += 1
                if retry_count > max_retries:
                    raise e
                sleep_time = min(30, 2 ** retry_count)
                print(f"  [YouTube Upload] Network interruption or socket drop ({type(e).__name__}: {e}). Resuming chunk in {sleep_time}s...")
                time.sleep(sleep_time)

        if response and "id" in response:
            return response["id"]
        return response.get("id") if response else None
    except HttpError as e:
        err_text = str(e)
        if "quotaExceeded" in err_text:
            _LAST_UPLOAD_ERROR = "YouTube Data API 10,000 daily quota exceeded for this Google Cloud project."
        elif "uploadLimitExceeded" in err_text:
            _LAST_UPLOAD_ERROR = "Channel daily upload limit exceeded (unverified phone quota or 24h reset cooldown)."
        else:
            _LAST_UPLOAD_ERROR = f"YouTube API HTTP {e.resp.status}: {err_text[:180]}"
        print(f"  [YouTube Upload] Error: {_LAST_UPLOAD_ERROR}")
        return None
    except Exception as e:
        err_text = str(e)
        if "invalid_grant" in err_text:
            _LAST_UPLOAD_ERROR = "OAuth token expired or revoked (invalid_grant). In Google Cloud Console, switch Publishing status from 'Testing' to 'In Production' and regenerate token."
        else:
            _LAST_UPLOAD_ERROR = f"Upload error ({type(e).__name__}): {err_text[:180]}"
        print(f"  [YouTube Upload] Error: {_LAST_UPLOAD_ERROR}")
        return None
