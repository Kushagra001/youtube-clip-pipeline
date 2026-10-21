"""Telegram Notification Module for YouTube Clipping Pipeline.

Sends instant real-time alerts for successful and failed YouTube Shorts uploads,
including clickable video links, attribution, and error diagnostics.
Requires:
  - TELEGRAM_BOT_TOKEN (from @BotFather)
  - TELEGRAM_CHAT_ID (from @userinfobot or channel ID)
"""
import os
import json
import urllib.request
import urllib.error
from html import escape


from dotenv import load_dotenv

load_dotenv()


def _get_telegram_creds() -> tuple[str | None, str | None]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if token:
        token = token.strip()
    if chat_id:
        chat_id = chat_id.strip()
    return token, chat_id


def send_telegram_message(message: str, parse_mode: str = "HTML") -> bool:
    """Sends a message to the configured Telegram chat via Bot API using standard library urllib."""
    token, chat_id = _get_telegram_creds()
    if not token or not chat_id:
        return False

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        print(f"  [Telegram] HTTP Error {e.code}: {error_body}")
        return False
    except Exception as e:
        print(f"  [Telegram] Notification failed: {e}")
        return False


def notify_upload_success(
    channel_name: str,
    handle: str,
    title: str,
    video_id: str,
    duration_sec: float | None = None,
    source_channel: str | None = None,
    tags: list[str] | None = None,
) -> bool:
    """Sends an attractive real-time notification when a Short is published publicly."""
    short_url = f"https://youtube.com/shorts/{video_id}"
    dur_str = f"{duration_sec:.1f}s" if duration_sec else "N/A"
    clean_title = escape(title)
    clean_channel = escape(channel_name)
    clean_handle = escape(handle)
    clean_source = escape(source_channel or "Original Creator")
    
    tag_str = ""
    if tags:
        clean_tags = [f"#{t.lstrip('#')}" for t in tags[:6]]
        tag_str = f"\n🏷️ <b>Tags:</b> {escape(' '.join(clean_tags))}"

    message = (
        f"🚀 <b>YouTube Short Published! [PUBLIC]</b>\n\n"
        f"📺 <b>Channel:</b> {clean_channel} (<code>{clean_handle}</code>)\n"
        f"🎬 <b>Title:</b> {clean_title}\n"
        f"⏱️ <b>Duration:</b> {dur_str}\n"
        f"👤 <b>Attribution:</b> {clean_source}\n"
        f"{tag_str}\n\n"
        f"🔗 <b>Watch Now:</b> <a href=\"{short_url}\">{short_url}</a>"
    )
    return send_telegram_message(message)


def notify_upload_failure(
    channel_name: str,
    handle: str,
    title: str,
    error_msg: str,
    url: str | None = None,
) -> bool:
    """Sends an immediate alert when an upload or video generation fails."""
    clean_title = escape(title)
    clean_channel = escape(channel_name)
    clean_handle = escape(handle)
    clean_error = escape(str(error_msg)[:300])

    source_line = f"\n🔗 <b>Source URL:</b> {escape(url)}" if url else ""

    message = (
        f"⚠️ <b>YouTube Short Upload Failed</b>\n\n"
        f"📺 <b>Channel:</b> {clean_channel} (<code>{clean_handle}</code>)\n"
        f"🎬 <b>Target:</b> {clean_title}\n"
        f"❌ <b>Error:</b> <code>{clean_error}</code>"
        f"{source_line}\n\n"
        f"<i>Please inspect GitHub Actions logs for full diagnostics.</i>"
    )
    return send_telegram_message(message)
