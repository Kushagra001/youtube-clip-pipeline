"""Aggregates per-channel run_summary JSON artifacts on workflow failure and dispatches consolidated alerts."""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import notifications


def _md_cell(text: str, max_len: int = 100) -> str:
    s = " ".join(str(text or "-").split()).replace("|", "/")
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s or "-"


def _load_reports(reports_dir: Path) -> list[dict]:
    if not reports_dir.exists():
        return []
    reports: list[dict] = []
    for p in sorted(reports_dir.rglob("run_summary_*.json")):
        try:
            reports.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[FailureSummary] Warning: could not parse {p}: {e}", file=sys.stderr)
    reports.sort(key=lambda r: str(r.get("channel_id", "")))
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Send consolidated workflow failure summary")
    parser.add_argument("--reports-dir", default="status_reports", help="Directory containing downloaded run_summary_*.json files")
    parser.add_argument("--setup-result", default="success", help="needs.setup.result")
    parser.add_argument("--clip-result", default="failure", help="needs.clip.result")
    parser.add_argument("--run-url", default="", help="GitHub Actions run URL")
    args = parser.parse_args()

    reports = _load_reports(Path(args.reports_dir))

    expected_channels: list[str] = []
    expected_raw = os.environ.get("EXPECTED_CHANNELS_JSON", "").strip()
    if expected_raw:
        try:
            parsed = json.loads(expected_raw)
            if isinstance(parsed, list):
                expected_channels = [str(x) for x in parsed if x]
        except Exception:
            expected_channels = []

    seen_cids = {str(r.get("channel_id", "")) for r in reports}
    for exp_cid in expected_channels:
        if exp_cid not in seen_cids and (args.setup_result == "success"):
            reports.append({
                "channel_id": exp_cid,
                "status": "failed",
                "job_status": "failure",
                "warp_display": "-",
                "oauth_status": "-",
                "clips_rendered": 0,
                "clips_uploaded": 0,
                "error_summary": "Job failed or timed out before uploading status report artifact.",
            })

    failed = [r for r in reports if r.get("status") != "passed" or r.get("job_status") not in (None, "", "success")]
    passed = [r for r in reports if r not in failed]

    if not failed and (args.setup_result != "success" or args.clip_result != "success"):
        failed = [{
            "channel_id": "setup" if args.setup_result != "success" else "clip_matrix",
            "warp_display": "-",
            "oauth_status": "-",
            "error_summary": f"Workflow failed (setup={args.setup_result}, clip={args.clip_result}) with no status report artifact.",
        }]

    total_channels = max(len(reports), len(failed) + len(passed), 1)
    passed_count = len(passed)

    # 1. Emit clean per-channel GitHub ::error:: annotations on the failure summary job
    for item in failed:
        cid = item.get("channel_id", "unknown")
        reason = re.sub(r"[\r\n]+", " ", str(item.get("error_summary") or item.get("oauth_status") or "Failed")).strip()
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error title=Failed Channel: {cid}::{reason[:280]}", flush=True)
        print(f"[FAILED] {cid}: {reason}")

    # 2. Write consolidated Markdown summary table to $GITHUB_STEP_SUMMARY
    rows = [
        "## 🚨 Workflow Failure Summary",
        "",
        f"**Passed:** {passed_count}/{total_channels} &nbsp;|&nbsp; **Failed:** {len(failed)}/{total_channels}",
        "",
        "| Channel | Status | WARP Egress | OAuth | Clips | Error / Diagnostics |",
        "|---|---|---|---|---|---|",
    ]
    for item in sorted(reports, key=lambda r: str(r.get("channel_id", ""))):
        is_ok = item in passed
        badge = "✅ Passed" if is_ok else "❌ Failed"
        clips_txt = f"{item.get('clips_rendered', 0)}/{item.get('clips_uploaded', 0)}"
        diag = item.get("error_summary") or "-"
        rows.append(
            f"| `{_md_cell(item.get('channel_id', '?'), 30)}` "
            f"| {badge} "
            f"| `{_md_cell(item.get('warp_display') or '-', 40)}` "
            f"| {_md_cell(item.get('oauth_status', '-'), 45)} "
            f"| {clips_txt} "
            f"| {_md_cell(diag, 110)} |"
        )
    if not reports:
        for item in failed:
            rows.append(
                f"| `{_md_cell(item.get('channel_id', '?'), 30)}` | ❌ Failed | - | - | 0/0 | {_md_cell(item.get('error_summary', '-'), 110)} |"
            )

    md_text = "\n".join(rows) + "\n"
    step_summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_file:
        with open(step_summary_file, "a", encoding="utf-8") as f:
            f.write(md_text)
    else:
        print(md_text)

    # 3. Dispatch consolidated Telegram + Discord notification
    run_url = args.run_url or None
    if failed:
        sent = notifications.notify_workflow_failure_summary(
            failed_channels=failed,
            total_channels=total_channels,
            passed_channels=passed_count,
            run_url=run_url,
        )
        print(f"[FailureSummary] Consolidated alert sent={sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
