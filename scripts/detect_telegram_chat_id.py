"""Helper script to detect or set Telegram Chat ID.

1. Open @MyClipPipelineBot in Telegram and press /start
2. Run `python scripts/detect_telegram_chat_id.py` to auto-detect and save your Chat ID to .env
Or pass --chat-id <id> directly if you already know it from @userinfobot.
"""
import os
import sys
import json
import argparse
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

if not TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN is missing in .env")
    sys.exit(1)

parser = argparse.ArgumentParser(description="Detect or set Telegram Chat ID")
parser.add_argument("--chat-id", type=str, default="", help="Directly set Chat ID if known (e.g. from @userinfobot)")
args = parser.parse_args()

if args.chat_id:
    chat_id = args.chat_id.strip()
    username = "Manual"
else:
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    print("Checking updates for bot token...")

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            updates = data.get("result", [])
            if not updates:
                print("\n❌ No messages received yet.")
                print("Please open Telegram, search for your bot, and send /start:")
                print("👉 https://t.me/MyClipPipelineBot")
                print("\nAlternatively, get your ID from https://t.me/userinfobot and run:")
                print("👉 python scripts/detect_telegram_chat_id.py --chat-id YOUR_ID\n")
                sys.exit(0)

            # Get latest message
            last_update = updates[-1]
            msg = last_update.get("message") or last_update.get("channel_post") or {}
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            user = msg.get("from", {})
            username = user.get("username") or chat.get("username") or chat.get("first_name")

            if not chat_id:
                print("Could not find chat ID in message payload.")
                sys.exit(1)
    except Exception as e:
        print(f"Error checking Telegram: {e}")
        sys.exit(1)

print(f"\n✅ Found Chat ID: {chat_id} (User: {username})")

# Save to .env
env_text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
lines = env_text.splitlines()
new_lines = []
found = False
for line in lines:
    if line.startswith("TELEGRAM_CHAT_ID="):
        new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
        found = True
    else:
        new_lines.append(line)
if not found:
    new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")

ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print(f"Saved TELEGRAM_CHAT_ID={chat_id} to .env!")

# Send confirmation test message
try:
    send_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": "🎉 <b>Telegram Alerts Connected!</b>\n\nYour YouTube Clipping Pipeline is now linked. You will receive real-time alerts whenever a Short is published publicly or if an issue occurs.",
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(send_url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as s_resp:
        print("Sent test notification message to your Telegram!")
except Exception as e:
    print(f"Warning: Failed to send test message: {e}")
