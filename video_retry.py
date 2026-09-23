#!/usr/bin/env python3
"""Retry loop for Agnes free-tier video generation (503 video_queue_full).

The free video queue (`agnes-video-2.5-flash`) is frequently saturated and
rejects submissions with HTTP 503 `video_queue_full`. This script keeps
submitting until the queue accepts the task, then polls until the video is
rendered and downloads it locally.

Background usage:

    cd <repo root>
    nohup python3 video_retry.py \
        --prompt "夜晚的森林中，一只发光的萤火虫绕着小鹿飞舞，镜头缓慢推进" \
        --seconds 5 --size 720P --aspect-ratio 16:9 --notify \
        > /tmp/agnes-video-retry.log 2>&1 &

Credentials come from the environment (AGNES_API_KEY / AGNES_BASE_URL) or the
repo-root `.env` — same as the MCP server. A macOS notification is sent on
success when --notify is passed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")
load_dotenv()  # also honor cwd/.env

from agnes_media_mcp import server  # noqa: E402


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def notify(title: str, message: str) -> None:
    if sys.platform != "darwin":
        return
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            check=False, capture_output=True,
        )
    except Exception:
        pass


def submit_until_accepted(args: argparse.Namespace) -> dict | None:
    """Submit until the queue accepts the task. max_submit_attempts=0 = forever."""
    attempt = 0
    while True:
        attempt += 1
        result = server._agnes_video_submit_impl(
            args.prompt,
            mode=args.mode,
            seconds=args.seconds,
            size=args.size,
            aspect_ratio=args.aspect_ratio,
            seed=args.seed,
            first_frame=args.first_frame,
            last_frame=args.last_frame,
            images=(args.images or None),
            audios=(args.audios or None),
            videos=None,  # reference videos must go through the paid model; use MCP tools instead
            include_raw=False,
        )
        if result.get("ok"):
            log(f"submitted on attempt {attempt}: video_id={result.get('video_id')}")
            return result

        error = result.get("error", {})
        code = str(error.get("code"))
        details = error.get("details") if isinstance(error, dict) else {}
        status_code = details.get("status_code") if isinstance(details, dict) else None
        message = str(error.get("message"))[:120]
        log(f"attempt {attempt}: {code} (HTTP {status_code}) {message}")

        # 400/401/403 are request or credential problems — retrying is pointless.
        if status_code in (400, 401, 403):
            log("non-retryable error — exiting.")
            return None
        if args.max_submit_attempts and attempt >= args.max_submit_attempts:
            log(f"gave up after {attempt} submit attempts.")
            return None
        time.sleep(args.interval)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retry Agnes free-tier video generation until the queue accepts it.")
    parser.add_argument("--prompt", required=True, help="video description")
    parser.add_argument("--mode", default="text", choices=("text", "keyframe", "reference"))
    parser.add_argument("--seconds", default="5", help="video length, string '4'-'12'")
    parser.add_argument("--size", default="720P",
                        help="720P/1080P/1K/2K (agnes-video-2.5-flash: 720P only)")
    parser.add_argument("--aspect-ratio", dest="aspect_ratio", default="16:9")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--first-frame", dest="first_frame", default=None)
    parser.add_argument("--last-frame", dest="last_frame", default=None)
    parser.add_argument("--images", nargs="+", default=None,
                        help="reference image URLs (mode=reference)")
    parser.add_argument("--audios", nargs="+", default=None,
                        help="reference audio URLs (mode=reference)")
    parser.add_argument("--max-submit-attempts", type=int, default=0,
                        help="0 (default) = keep retrying forever until accepted")
    parser.add_argument("--interval", type=int, default=600,
                        help="seconds between submit attempts (default 600)")
    parser.add_argument("--wait-timeout", type=int, default=600,
                        help="max polling seconds after submission (default 600)")
    parser.add_argument("--poll-interval", type=int, default=6)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--output-filename", default=None)
    parser.add_argument("--notify", action="store_true",
                        help="send a macOS notification when the video is ready")
    args = parser.parse_args()

    if not (os.getenv("AGNES_API_KEY") or (REPO_ROOT / ".env").exists()):
        log("AGNES_API_KEY is missing — set the env var or create .env from .env.example.")
        return 2

    submitted = submit_until_accepted(args)
    if not submitted:
        notify("Agnes video", "submit failed — see log")
        return 1

    video_id = submitted.get("video_id")
    log(f"polling {video_id} every {args.poll_interval}s (timeout {args.wait_timeout}s)...")
    wait = server._agnes_video_wait_impl(
        video_id,
        timeout_seconds=args.wait_timeout,
        poll_interval_seconds=args.poll_interval,
        download=not args.no_download,
        output_filename=args.output_filename,
    )
    if not wait.get("ok"):
        log("wait failed: " + json.dumps(wait, ensure_ascii=False)[:240])
        notify("Agnes video", "wait failed — see log")
        return 1

    log(f"DONE: url={wait.get('video_url')}")
    log(f"DONE: local={wait.get('local_path')}")
    if args.notify:
        notify("Agnes video ready", str(wait.get("local_path") or wait.get("video_url") or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
