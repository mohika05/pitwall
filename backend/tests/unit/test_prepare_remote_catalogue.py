from argparse import Namespace
from datetime import UTC, datetime, timedelta

from scripts import prepare_remote_catalogue


def test_remote_catalogue_requests_only_due_incomplete_sessions(monkeypatch):
    due = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    future = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    catalog = {
        "meetings": [
            {
                "meeting_name": "Bahrain Grand Prix",
                "sessions": [
                    {
                        "session_key": 11727,
                        "session_name": "Practice 1",
                        "date_end": due,
                        "telemetry_available": False,
                    },
                    {
                        "session_key": 11728,
                        "session_name": "Practice 2",
                        "date_end": due,
                        "telemetry_available": True,
                    },
                    {
                        "session_key": 11729,
                        "session_name": "Practice 3",
                        "date_end": future,
                        "telemetry_available": False,
                    },
                ],
            },
            {
                "meeting_name": "Pre-Season Testing",
                "sessions": [
                    {
                        "session_key": 11700,
                        "session_name": "Day 1",
                        "date_end": due,
                        "telemetry_available": False,
                    }
                ],
            },
        ]
    }
    posts = []

    def fake_request(url, *, admin_token=None, payload=None, retry_attempts=4):
        if payload is None:
            return catalog
        posts.append((url, admin_token, payload, retry_attempts))
        return {"state": "queued"}

    monkeypatch.setattr(prepare_remote_catalogue, "request_json", fake_request)
    monkeypatch.setattr(
        prepare_remote_catalogue,
        "wait_for_job",
        lambda *_args: {"state": "ready", "errors": []},
    )

    result = prepare_remote_catalogue.run(
        Namespace(
            api_url="https://pitwall.example",
            admin_token="secret",
            year=2026,
            recent_days=30,
            completion_delay_minutes=120,
        )
    )

    assert result == 0
    assert posts == [
        (
            "https://pitwall.example/api/preparation/11727",
            "secret",
            {"telemetry": True},
            4,
        )
    ]
