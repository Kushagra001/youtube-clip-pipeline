"""Multi-Platform Notification Module for YouTube Clipping Pipeline.

Sends instant real-time alerts for successful, scheduled, and failed YouTube Shorts uploads,
including clickable video links, attribution, thumbnails, and error diagnostics across:
  - Telegram (via Bot API)
  - Discord (via Incoming Webhooks with rich embeds)
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


def _get_discord_webhook() -> str | None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    return webhook.strip() if webhook else None


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

    import time
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            if e.code == 429 and attempt == 0:
                print("  [Telegram] Rate limit encountered (HTTP 429). Retrying in 2s...")
                time.sleep(2.0)
                continue
            print(f"  [Telegram] HTTP Error {e.code}: {error_body}")
            return False
        except Exception as e:
            print(f"  [Telegram] Notification failed: {e}")
            return False
    return False


def send_discord_message(payload: dict) -> bool:
    """Sends a rich embed notification to the configured Discord Webhook."""
    webhook_url = _get_discord_webhook()
    if not webhook_url:
        return False

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "YouTubeClipPipeline/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status in (200, 204)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        print(f"  [Discord] HTTP Error {e.code}: {error_body}")
        return False
    except Exception as e:
        print(f"  [Discord] Notification failed: {e}")
        return False


def notify_upload_success(
    channel_name: str,
    handle: str,
    title: str,
    video_id: str,
    duration_sec: float | None = None,
    source_channel: str | None = None,
    tags: list[str] | None = None,
    privacy_status: str = "public",
    scheduled_at: str | None = None,
) -> bool:
    """Sends real-time alerts to Telegram and Discord when a Short is published or scheduled."""
    short_url = f"https://youtube.com/shorts/{video_id}"
    dur_str = f"{duration_sec:.1f}s" if duration_sec else "N/A"
    clean_title = escape(title)
    clean_channel = escape(channel_name)
    clean_handle = escape(handle)
    clean_source = escape(source_channel or "Original Creator")
    
    is_scheduled = bool(scheduled_at) or privacy_status.lower() == "scheduled"
    status_label = f"SCHEDULED ({scheduled_at})" if is_scheduled else privacy_status.upper()
    header_emoji = "📅" if is_scheduled else "🚀"
    header_text = "YouTube Short Scheduled!" if is_scheduled else "YouTube Short Published!"

    tag_str = ""
    clean_tags = []
    if tags:
        clean_tags = [f"#{t.lstrip('#')}" for t in tags[:6]]
        tag_str = f"\n🏷️ <b>Tags:</b> {escape(' '.join(clean_tags))}"

    schedule_line = f"\n⏰ <b>Scheduled For:</b> <code>{escape(scheduled_at or '')}</code>" if scheduled_at else ""

    # 1. Telegram Alert
    tg_message = (
        f"{header_emoji} <b>{header_text} [{status_label}]</b>\n\n"
        f"📺 <b>Channel:</b> {clean_channel} (<code>{clean_handle}</code>)\n"
        f"🎬 <b>Title:</b> {clean_title}\n"
        f"⏱️ <b>Duration:</b> {dur_str}\n"
        f"👤 <b>Attribution:</b> {clean_source}"
        f"{schedule_line}"
        f"{tag_str}\n\n"
        f"🔗 <b>Watch Link:</b> <a href=\"{short_url}\">{short_url}</a>"
    )
    tg_sent = send_telegram_message(tg_message)

    # 2. Discord Alert (Rich Embed)
    embed_color = 0x00E5FF if is_scheduled else (0x00FF66 if privacy_status == "public" else 0xF59E0B)
    fields = [
        {"name": "📺 Channel", "value": f"{channel_name} (`{handle}`)", "inline": True},
        {"name": "⏱️ Duration", "value": dur_str, "inline": True},
        {"name": "👤 Attribution", "value": source_channel or "Original Creator", "inline": True},
    ]
    if scheduled_at:
        fields.append({"name": "⏰ Scheduled Release", "value": f"`{scheduled_at}`", "inline": False})
    if clean_tags:
        fields.append({"name": "🏷️ Tags", "value": " ".join(clean_tags), "inline": False})

    discord_payload = {
        "embeds": [
            {
                "title": f"{header_emoji} {header_text} [{status_label}]",
                "description": f"**[{title}]({short_url})**",
                "url": short_url,
                "color": embed_color,
                "fields": fields,
                "thumbnail": {
                    "url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                },
                "footer": {
                    "text": "YouTube Shorts Autonomous Pipeline"
                }
            }
        ]
    }
    discord_sent = send_discord_message(discord_payload)

    return tg_sent or discord_sent


def notify_upload_failure(
    channel_name: str,
    handle: str,
    title: str,
    error_msg: str,
    url: str | None = None,
) -> bool:
    """Sends an immediate alert to Telegram and Discord when an upload or video generation fails."""
    clean_title = escape(title)
    clean_channel = escape(channel_name)
    clean_handle = escape(handle)
    clean_error = escape(str(error_msg)[:300])

    source_line = f"\n🔗 <b>Source URL:</b> {escape(url)}" if url else ""

    # 1. Telegram Alert
    tg_message = (
        f"⚠️ <b>YouTube Short Upload Failed</b>\n\n"
        f"📺 <b>Channel:</b> {clean_channel} (<code>{clean_handle}</code>)\n"
        f"🎬 <b>Target:</b> {clean_title}\n"
        f"❌ <b>Error:</b> <code>{clean_error}</code>"
        f"{source_line}\n\n"
        f"<i>Please inspect GitHub Actions logs for full diagnostics.</i>"
    )
    tg_sent = send_telegram_message(tg_message)

    # 2. Discord Alert
    fields = [
        {"name": "📺 Channel", "value": f"{channel_name} (`{handle}`)", "inline": True},
        {"name": "🎬 Target Title", "value": title[:200], "inline": False},
        {"name": "❌ Error Diagnostics", "value": f"```{str(error_msg)[:500]}```", "inline": False},
    ]
    if url:
        fields.append({"name": "🔗 Source URL", "value": url, "inline": False})

    discord_payload = {
        "embeds": [
            {
                "title": "⚠️ YouTube Short Upload Failed",
                "description": "An unexpected error occurred during clipping or YouTube Data API upload.",
                "color": 0xEF4444,
                "fields": fields,
                "footer": {
                    "text": "YouTube Shorts Autonomous Pipeline • Diagnostics"
                }
            }
        ]
    }
    discord_sent = send_discord_message(discord_payload)

    return tg_sent or discord_sent

