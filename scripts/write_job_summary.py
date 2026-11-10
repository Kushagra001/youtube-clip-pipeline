"""Writes a per-channel GitHub Actions Step Summary Markdown table and enriches run_summary JSON."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _md_cell(text: str, max_len: int = 120) -> str:
    s = " ".join(str(text or "-").split()).replace("|", "/")
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s or "-"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write per-job GitHub Step Summary")
    parser.add_argument("--channel", required=True, help="Matrix channel identifier")
    parser.add_argument("--job-status", default="success", help="GitHub Actions job.status")
    args = parser.parse_args()

    safe_cid = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in args.channel)
    summary_path = ROOT / "output" / f"run_summary_{safe_cid}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    if summary_path.exists():
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    warp_path = os.environ.get("WARP_EGRESS_PATH", "").strip()
    warp_ip = os.environ.get("WARP_EGRESS_IP", "").strip()
    warp_display = f"{warp_path} ({warp_ip})" if warp_path and warp_ip else (warp_path or warp_ip or "Direct / Unknown")

    data.setdefault("channel_id", args.channel)
    data.setdefault("channel_name", args.channel)
    data.setdefault("handle", "")
    data["warp_path"] = warp_path
    data["warp_ip"] = warp_ip
    data["warp_display"] = warp_display
    data["job_status"] = args.job_status

    if args.job_status != "success" and data.get("status") != "failed":
        data["status"] = "failed"
        if not data.get("error_summary"):
            data["error_summary"] = f"Job exited with status '{args.job_status}' before pipeline completion."
    elif "status" not in data:
        data["status"] = "passed" if args.job_status == "success" else "failed"

    summary_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    selected = data.get("selected_videos") or []
    sel_text = (
        "; ".join(
            f"{v.get('video_id', '?')} ({_md_cell(v.get('title', ''), 36)})"
            for v in selected[:2]
        )
        if selected
        else "None"
    )
    rendered = data.get("clips_rendered", 0)
    uploaded = data.get("clips_uploaded", 0)
    skipped_quota = data.get("upload_skipped_quota", 0)
    upload_text = f"{rendered} rendered / {uploaded} uploaded"
    if skipped_quota:
        upload_text += f" ({skipped_quota} quota-capped, saved as artifact)"

    badge = "✅ Passed" if data.get("status") == "passed" else "❌ Failed"
    oauth_txt = data.get("oauth_status", "Unknown")
    diag_txt = data.get("error_summary") or "Clean run"

    md_lines = [
        f"### {badge} — {data.get('channel_name', args.channel)} (`{args.channel}`)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Status** | {_md_cell(badge)} |",
        f"| **WARP Egress** | `{_md_cell(warp_display, 90)}` |",
        f"| **OAuth Pre-Flight** | {_md_cell(oauth_txt, 110)} |",
        f"| **Selected Videos** | {_md_cell(sel_text, 140)} |",
        f"| **Clips / Uploads** | {_md_cell(upload_text, 100)} |",
        f"| **Diagnostics** | {_md_cell(diag_txt, 160)} |",
        "",
    ]

    step_summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_file:
        with open(step_summary_file, "a", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")
    else:
        print("\n".join(md_lines))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

