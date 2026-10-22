import time
import json
from pathlib import Path

BASE_STATE_DIR = Path(__file__).resolve().parent.parent / "state"
DEFAULT_STATE_PATH = BASE_STATE_DIR / "processed.json"


def _get_state_path(channel_id: str | None = None) -> Path:
    if not channel_id or channel_id == "default":
        return DEFAULT_STATE_PATH
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in channel_id)
    return BASE_STATE_DIR / f"processed_{safe_name}.json"


def load_state(channel_id: str | None = None) -> dict:
    state_file = _get_state_path(channel_id)
    if not state_file.exists():
        return {"processed_video_ids": [], "upload_timestamps": []}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"processed_video_ids": [], "upload_timestamps": []}
            return json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [State] Warning: Could not decode {state_file.name} ({e}). Recovering with clean state.")
        return {"processed_video_ids": [], "upload_timestamps": []}


def save_state(state: dict, channel_id: str | None = None) -> None:
    state_file = _get_state_path(channel_id)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = state_file.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(state_file)
    except Exception as e:
        # Fallback to direct write if rename fails (e.g. certain file system locks)
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as write_err:
            print(f"  [State] Critical error saving state to {state_file.name}: {write_err}")
        if temp_file.exists():
            try:
                temp_file.unlink(missing_ok=True)
            except Exception:
                pass


def is_processed(state: dict, video_id: str) -> bool:
    return video_id in state.get("processed_video_ids", [])


def mark_processed(state: dict, video_id: str) -> None:
    ids = state.setdefault("processed_video_ids", [])
    if video_id not in ids:
        ids.append(video_id)


def can_upload(state: dict, max_uploads_per_day: int = 5) -> bool:
    """Checks if we are within the daily quota budget (default max 5 uploads/day = 8,000 quota units)."""
    now = time.time()
    one_day_ago = now - 86400
    timestamps = [t for t in state.get("upload_timestamps", []) if t > one_day_ago]
    state["upload_timestamps"] = timestamps
    return len(timestamps) < max_uploads_per_day


def record_upload(state: dict) -> None:
    """Records an upload timestamp to track YouTube Data API quota usage."""
    timestamps = state.setdefault("upload_timestamps", [])
    timestamps.append(time.time())
