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


def _get_service(token_env_var: str | None = None):
    refresh_token = None
    if token_env_var:
        refresh_token = os.environ.get(token_env_var)
    if not refresh_token:
        refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not refresh_token:
        var_name = token_env_var or "YOUTUBE_REFRESH_TOKEN"
        raise ValueError(f"Missing YouTube refresh token in environment variable: {var_name}")

    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("Missing YOUTUBE_CLIENT_ID or YOUTUBE_CLIENT_SECRET in environment")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds)


def upload_short(
    video_path: str,
    title: str,
    description: str,
    privacy_status: str = "private",
    category_id: str = "24",
    tags: list[str] | None = None,
    token_env_var: str | None = None,
    made_for_kids: bool = False,
) -> str | None:
    """Uploads a vertical Short to YouTube with resumable chunking and quota error protection."""
    from googleapiclient.errors import HttpError

    try:
        youtube = _get_service(token_env_var=token_env_var)
    except Exception as e:
        print(f"  [YouTube Upload] Authentication error: {e}")
        return None

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "categoryId": category_id,
            "tags": tags or ["#shorts", "shorts", "viral", "podcast", "clips"],
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
            "embeddable": True,
        },
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
                retry_count += 1
                if retry_count > max_retries:
                    raise e
                sleep_time = min(30, 2 ** retry_count)
                print(f"  [YouTube Upload] Network interruption ({e}). Resuming chunk in {sleep_time}s...")
                time.sleep(sleep_time)

        if response and "id" in response:
            return response["id"]
        return response.get("id") if response else None
    except HttpError as e:
        if "quotaExceeded" in str(e):
            print("  [YouTube Upload] Warning: Daily YouTube Data API upload quota exceeded.")
        else:
            print(f"  [YouTube Upload] HTTP error during upload: {e}")
        return None
    except Exception as e:
        print(f"  [YouTube Upload] Unexpected upload error: {e}")
        return None
