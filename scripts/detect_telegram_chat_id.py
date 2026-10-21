"""Helper script to detect Telegram Chat ID automatically.

Once you open @MyClipPipelineBot in Telegram and press /start,
this script detects your Chat ID, saves it into .env, and sends a test message.
"""
import os
import sys
import json
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

url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
print(f"Checking updates for bot token...")

try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        updates = data.get("result", [])
        if not updates:
            print("\n❌ No messages received yet.")
            print("Please open Telegram, search for your bot, and send /start:")
            print("👉 https://t.me/MyClipPipelineBot\n")
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
    print(f"Error checking Telegram: {e}")
