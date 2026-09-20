import argparse
import asyncio

from app.ingestion.providers.fastf1 import (
    FastF1TelemetryProvider,
)
from app.persistence.database import (
    AsyncSessionLocal,
)
from app.persistence.repositories.session_repository import (
    SessionRepository,
)


async def run(
    session_key: int,
    event: str,
    driver: str | None,
    ingest_all: bool,
) -> None:
    # ---------------------------------------------------------
    # LOAD PITWALL SESSION CONTEXT
    # ---------------------------------------------------------

    async with AsyncSessionLocal() as db:
        context = await SessionRepository(
            db
        ).get_replay_context(
            session_key
        )

    year = context.session.year

    # ---------------------------------------------------------
    # LOAD FASTF1 SESSION ONCE
    # ---------------------------------------------------------

    provider = (
        FastF1TelemetryProvider()
    )

    print(
        f"Loading FastF1 race: "
        f"{year} {event}"
    )

    session = await provider.load_session(
        year=year,
        event=event,
        session_type="R",
    )

    print(
        "FastF1 session loaded."
    )

    # ---------------------------------------------------------
    # DETERMINE DRIVERS
    # ---------------------------------------------------------

    if ingest_all:
        drivers = [
            item.name_acronym
            for item in context.drivers
            if item.name_acronym
        ]

    elif driver:
        drivers = [
            driver.upper()
        ]

    else:
        raise ValueError(
            (
                "Specify either --driver "
                "or --all"
            )
        )

    # ---------------------------------------------------------
    # EXTRACT + SAVE
    # ---------------------------------------------------------

    successful = 0
    failed = 0

    print()
    print(
        f"Processing {len(drivers)} "
        "driver(s)..."
    )
    print()

    for current_driver in drivers:
        print(
            f"[{current_driver}] "
            "Extracting telemetry..."
        )

        try:
            telemetry = (
                await provider.extract_driver(
                    session,
                    current_driver,
                )
            )

            export = (
                await provider.export_driver(
                    session_key,
                    telemetry,
                )
            )

        except Exception as exc:
            failed += 1

            print(
                f"[{current_driver}] FAILED"
            )

            print(
                f"  {type(exc).__name__}: "
                f"{exc}"
            )

            continue

        successful += 1

        print(
            f"[{current_driver}] OK"
        )

        print(
            f"  Car rows:      "
            f"{export.car_rows:,}"
        )

        print(
            f"  Position rows: "
            f"{export.position_rows:,}"
        )

        print(
            f"  Car file:      "
            f"{export.car_path}"
        )

        print(
            f"  Position file: "
            f"{export.position_path}"
        )

        print()

    # ---------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------

    print()
    print("Telemetry ingestion finished.")

    print(
        f"Successful: {successful}"
    )

    print(
        f"Failed:     {failed}"
    )

    if failed:
        raise RuntimeError(
            (
                f"{failed} telemetry "
                "driver(s) failed"
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--session-key",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--event",
        required=True,
        help=(
            "FastF1 event identifier, "
            "for example Singapore"
        ),
    )

    group = (
        parser.add_mutually_exclusive_group(
            required=True
        )
    )

    group.add_argument(
        "--driver",
        help=(
            "Single FastF1 driver "
            "abbreviation, e.g. RUS"
        ),
    )

    group.add_argument(
        "--all",
        action="store_true",
        dest="ingest_all",
        help=(
            "Extract telemetry for "
            "every driver"
        ),
    )

    args = parser.parse_args()

    asyncio.run(
        run(
            session_key=(
                args.session_key
            ),
            event=args.event,
            driver=args.driver,
            ingest_all=(
                args.ingest_all
            ),
        )
    )

if __name__ == "__main__":
    main()