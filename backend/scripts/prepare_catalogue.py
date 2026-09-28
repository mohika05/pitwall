"""Prepare historical sessions sequentially through a running Pitwall API."""

import argparse
import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path

import httpx

TERMINAL = {"ready", "partial", "failed", "interrupted"}


async def wait_for_job(client: httpx.AsyncClient, session_key: int) -> dict:
    while True:
        response = await client.get(f"/preparation/{session_key}")
        response.raise_for_status()
        job = response.json()
        print(
            f"{session_key}: {job['state']} {job['progress']}% {job['message']}",
            flush=True,
        )
        if job["state"] in TERMINAL:
            return job
        await asyncio.sleep(5)


async def run(args: argparse.Namespace) -> int:
    failures = 0
    processed = 0
    headers = {"X-Pitwall-Admin": args.admin_token} if args.admin_token else {}
    async with httpx.AsyncClient(
        base_url=args.api_url.rstrip("/") + "/api",
        headers=headers,
        timeout=60,
    ) as client:
        years = args.years
        if not years:
            response = await client.get("/catalog/years")
            response.raise_for_status()
            years = response.json()["years"]
        for year in years:
            response = await client.get(f"/catalog/{year}")
            response.raise_for_status()
            sessions = [
                session
                for meeting in response.json()["meetings"]
                if "testing" not in str(meeting.get("meeting_name", "")).lower()
                for session in meeting["sessions"]
                if not session.get("is_cancelled")
                and session.get("date_start")
                and datetime.fromisoformat(session["date_start"]) <= datetime.now(UTC)
                and (
                    not args.session_keys
                    or int(session["session_key"]) in args.session_keys
                )
            ]
            for session in sessions:
                if args.max_sessions is not None and processed >= args.max_sessions:
                    print(f"Stopped after {processed} requested sessions")
                    return 1 if failures else 0
                key = int(session["session_key"])
                if session.get("telemetry_available") and not args.force:
                    print(f"{key}: already ready")
                    continue
                free_gb = shutil.disk_usage(Path.cwd()).free / 1_000_000_000
                if free_gb < args.min_free_gb:
                    raise RuntimeError(
                        f"Only {free_gb:.2f} GB is free; refusing to start session {key} "
                        f"below the {args.min_free_gb:.2f} GB safety floor"
                    )
                job = None
                for attempt in range(args.retry_attempts + 1):
                    response = await client.post(
                        f"/preparation/{key}", json={"telemetry": not args.timing_only}
                    )
                    response.raise_for_status()
                    job = await wait_for_job(client, key)
                    if job["state"] == "ready":
                        break
                    if "OpenF1 returned 401" in str(job.get("message", "")):
                        print(
                            "OpenF1 historical access is temporarily locked during "
                            "a live F1 session; stop and resume after the session ends.",
                            flush=True,
                        )
                        return 1
                    if attempt < args.retry_attempts:
                        print(
                            f"{key}: retrying after {job['state']} "
                            f"({attempt + 1}/{args.retry_attempts})",
                            flush=True,
                        )
                processed += 1
                assert job is not None
                if job["state"] != "ready":
                    failures += 1
                    print(f"{key}: requires attention: {job.get('errors', [])}")
                    if args.stop_on_error:
                        return 1
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--years", nargs="*", type=int, default=[])
    parser.add_argument("--admin-token")
    parser.add_argument("--timing-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--retry-attempts", type=int, default=1)
    parser.add_argument("--min-free-gb", type=float, default=3.0)
    parser.add_argument("--max-sessions", type=int)
    parser.add_argument("--session-keys", nargs="*", type=int, default=[])
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
