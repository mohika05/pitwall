"""Prepare recent sessions through a deployed Pitwall API.

This runner deliberately performs no ingestion work itself. It lets a scheduler such
as GitHub Actions discover incomplete sessions, asks the deployed backend to prepare
them, and keeps polling until each backend job reaches a terminal state.
"""

import argparse
import json
import os
import time
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TERMINAL_STATES = {"ready", "partial", "failed", "interrupted"}
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_DELAYS_SECONDS = (10, 30, 60, 120)


def request_json(
    url: str,
    *,
    admin_token: str | None = None,
    payload: dict | None = None,
    retry_attempts: int = 4,
) -> dict:
    headers = {"Accept": "application/json"}
    if admin_token:
        headers["X-Pitwall-Admin"] = admin_token
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()

    for attempt in range(retry_attempts + 1):
        request = Request(url, headers=headers, data=data)
        try:
            with urlopen(request, timeout=90) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in TRANSIENT_STATUS_CODES or attempt >= retry_attempts:
                detail = exc.read().decode(errors="replace")
                raise RuntimeError(f"{url} returned HTTP {exc.code}: {detail}") from exc
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else None
            except ValueError:
                delay = None
        except URLError as exc:
            if attempt >= retry_attempts:
                raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc
            delay = None

        delay = delay or RETRY_DELAYS_SECONDS[min(attempt, len(RETRY_DELAYS_SECONDS) - 1)]
        print(f"Temporary API failure; retrying in {delay:g}s", flush=True)
        time.sleep(delay)

    raise RuntimeError("Unreachable request retry state")


def is_due(session: dict, now: datetime, args: argparse.Namespace) -> bool:
    timestamp = session.get("date_end") or session.get("date_start")
    if not timestamp:
        return False
    ended_at = datetime.fromisoformat(timestamp)
    if ended_at > now - timedelta(minutes=args.completion_delay_minutes):
        return False
    return not (
        args.recent_days is not None
        and ended_at < now - timedelta(days=args.recent_days)
    )


def wait_for_job(api_url: str, session_key: int, admin_token: str) -> dict:
    while True:
        job = request_json(
            f"{api_url}/api/preparation/{session_key}",
            admin_token=admin_token,
        )
        print(
            f"{session_key}: {job['state']} {job['progress']}% {job['message']}",
            flush=True,
        )
        if job["state"] in TERMINAL_STATES:
            return job
        time.sleep(10)


def run(args: argparse.Namespace) -> int:
    if not args.admin_token:
        raise RuntimeError("PITWALL_ADMIN_TOKEN is required")

    api_url = args.api_url.rstrip("/")
    catalog = request_json(f"{api_url}/api/catalog/{args.year}")
    now = datetime.now(UTC)
    sessions = [
        session
        for meeting in catalog["meetings"]
        if "testing" not in str(meeting.get("meeting_name", "")).lower()
        for session in meeting["sessions"]
        if not session.get("is_cancelled")
        and not session.get("telemetry_available")
        and is_due(session, now, args)
    ]

    if not sessions:
        print(f"No incomplete {args.year} sessions are due for ingestion.")
        return 0

    failures = 0
    print(f"Requesting {len(sessions)} incomplete session(s) from {api_url}")
    for session in sessions:
        session_key = int(session["session_key"])
        label = f"{session.get('meeting_name', 'Unknown meeting')} {session.get('session_name', '')}"
        print(f"{session_key}: starting {label.strip()}", flush=True)
        request_json(
            f"{api_url}/api/preparation/{session_key}",
            admin_token=args.admin_token,
            payload={"telemetry": True},
        )
        job = wait_for_job(api_url, session_key, args.admin_token)
        if job["state"] != "ready":
            failures += 1
            print(f"{session_key}: requires attention: {job.get('errors', [])}")

    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--admin-token", default=os.environ.get("PITWALL_ADMIN_TOKEN"))
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--recent-days", type=float, default=30)
    parser.add_argument("--completion-delay-minutes", type=float, default=120)
    raise SystemExit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
