"""Run this ONCE, locally (not in CI), to obtain a refresh token for the
YouTube Data API. Prints the values you need to add as GitHub Actions
secrets: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN.

Prereqs:
1. In Google Cloud Console, create an OAuth 2.0 Client ID (type: Desktop app)
   under a project that has the YouTube Data API v3 enabled.
2. Download the client secret JSON and point CLIENT_SECRETS_FILE at it.
"""
import sys
import argparse
from pathlib import Path
import yaml
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_SECRETS_FILE = "client_secret.json"  # downloaded from Google Cloud Console
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CHANNELS_DIR = Path(__file__).resolve().parent.parent / "config" / "channels"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _resolve_token_var(channel_query: str) -> str:
    if not channel_query:
        return "YOUTUBE_REFRESH_TOKEN"
    if CHANNELS_DIR.exists():
        for p in CHANNELS_DIR.glob("*.yaml"):
            if p.stem == channel_query or p.stem.startswith(channel_query) or channel_query.lower() in p.stem.lower():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        token_var = data.get("youtube", {}).get("token_env_var")
                        if token_var:
                            return token_var
                except Exception:
                    pass
    suffix = channel_query.upper().replace("-", "_")
    return f"YOUTUBE_REFRESH_TOKEN_{suffix}"


def _save_to_env(client_id: str, client_secret: str, token_var: str, refresh_token: str):
    env_content = ""
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            env_content = f.read()

    lines = env_content.splitlines()
    updates = {
        "YOUTUBE_CLIENT_ID": client_id,
        "YOUTUBE_CLIENT_SECRET": client_secret,
        token_var: refresh_token,
    }

    new_lines = []
    seen = set()
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in seen:
            new_lines.append(f"{k}={v}")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")


class UrlSaver:
    def format(self, url: str) -> str:
        clean_url = url.strip()
        auth_file = Path(__file__).resolve().parent.parent / "auth_url.txt"
        with open(auth_file, "w", encoding="utf-8") as f:
            f.write(clean_url)
        return (
            "\n"
            "=======================================================\n"
            " 📋 Authorization URL Generated!\n"
            "=======================================================\n"
            f" Clean URL saved to: {auth_file.name}\n"
            " Simply open 'auth_url.txt', copy the clean line,\n"
            " and paste it into your other browser.\n"
            "=======================================================\n"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate YouTube OAuth refresh token.")
    parser.add_argument("--channel", type=str, default="", help="Channel ID or name (e.g. acc_01, acc_02_dogs)")
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0, authorization_prompt_message=UrlSaver())

    token_var = _resolve_token_var(args.channel)
    _save_to_env(creds.client_id, creds.client_secret, token_var, creds.refresh_token)

    print("\n=======================================================")
    print(" ✅ YouTube OAuth Authentication Successful!")
    print("=======================================================")
    print(f"Client ID:      {creds.client_id}")
    print(f"Client Secret:  {creds.client_secret}")
    print(f"Refresh Token:  {creds.refresh_token}")
    print(f"Target Env Var: {token_var}")
    print(f"\nSaved automatically to: {ENV_PATH.name}")
    print("\nFor GitHub Actions, add these to GitHub Repo Secrets:")
    print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"{token_var}={creds.refresh_token}")
    print("=======================================================\n")
