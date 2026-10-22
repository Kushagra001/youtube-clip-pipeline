"""Helper script to save YouTube cookies locally and upload to GitHub Secrets.

Usage:
  python scripts/set_youtube_cookies.py [path_to_cookies.txt]
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from base64 import b64encode
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
COOKIES_DEST = PROJECT_ROOT / "output" / "cookies.txt"


def main():
    if len(sys.argv) > 1:
        source_path = Path(sys.argv[1])
        if not source_path.exists():
            print(f"Error: File not found at {source_path}")
            sys.exit(1)
        cookie_data = source_path.read_text(encoding="utf-8")
    else:
        print("Please enter the path to your exported cookies.txt file:")
        user_input = input("File path: ").strip().strip('"').strip("'")
        source_path = Path(user_input)
        if not source_path.exists():
            print(f"Error: File not found at {source_path}")
            sys.exit(1)
        cookie_data = source_path.read_text(encoding="utf-8")

    if not cookie_data.strip():
        print("Error: Cookie file is empty.")
        sys.exit(1)

    # 1. Save locally to output/cookies.txt (git-ignored)
    COOKIES_DEST.parent.mkdir(parents=True, exist_ok=True)
    COOKIES_DEST.write_text(cookie_data, encoding="utf-8")
    print(f"✅ Saved cookies locally to {COOKIES_DEST}")

    # 2. Upload to GitHub Secrets via GitHub API
    try:
        from nacl import encoding, public

        token_cmd = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n",
            capture_output=True,
            text=True,
        )
        token = [
            line.split("password=")[1]
            for line in token_cmd.stdout.splitlines()
            if line.startswith("password=")
        ][0]

        # Fetch public key
        import urllib.request

        req = urllib.request.Request(
            "https://api.github.com/repos/Kushagra001/youtube-clip-pipeline/actions/secrets/public-key",
            headers={"Authorization": f"token {token}", "User-Agent": "Mozilla/5.0"},
        )
        key_data = json.loads(urllib.request.urlopen(req).read())
        key_id = key_data["key_id"]
        pub_key_str = key_data["key"]

        # Encrypt value
        pub_key = public.PublicKey(pub_key_str.encode("utf-8"), encoding.Base64Encoder)
        sealed_box = public.SealedBox(pub_key)
        encrypted_bytes = sealed_box.encrypt(cookie_data.encode("utf-8"))
        encrypted_val = b64encode(encrypted_bytes).decode("utf-8")

        # PUT secret
        put_url = "https://api.github.com/repos/Kushagra001/youtube-clip-pipeline/actions/secrets/YOUTUBE_COOKIES"
        payload = json.dumps({"encrypted_value": encrypted_val, "key_id": key_id}).encode("utf-8")
        put_req = urllib.request.Request(
            put_url,
            data=payload,
            headers={"Authorization": f"token {token}", "User-Agent": "Mozilla/5.0"},
            method="PUT",
        )
        with urllib.request.urlopen(put_req) as resp:
            if resp.status in (201, 204):
                print("✅ Successfully uploaded YOUTUBE_COOKIES to GitHub Secrets!")
            else:
                print(f"Uploaded with status code: {resp.status}")
    except Exception as e:
        print(f"Note: Could not automatically push to GitHub Secrets ({e}).")
        print("You can manually add the secret on GitHub: Settings > Secrets and variables > Actions > YOUTUBE_COOKIES")


if __name__ == "__main__":
    main()
