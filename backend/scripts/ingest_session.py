import argparse
import asyncio

from app.ingestion.providers.openf1 import (
    OpenF1Provider,
)
from app.ingestion.service import (
    IngestionService,
)
from app.persistence.database import (
    AsyncSessionLocal,
)
from app.persistence.repositories.event_repository import (
    EventRepository,
)
from app.persistence.repositories.ingestion_repository import (
    IngestionRepository,
)


async def run(
    year: int,
    country: str,
    refresh: bool,
) -> None:
    async with OpenF1Provider() as provider:
        service = IngestionService(
            provider
        )

        bundle = await service.get_bundle(
            year=year,
            country_name=country,
            refresh=refresh,
        )

    context, events = (
        service.normalize(
            bundle
        )
    )

    processed_path = (
        service.save_processed_events(
            context.session.session_key,
            events,
        )
    )

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await IngestionRepository(
                db
            ).persist_bundle(
                bundle
            )

            await EventRepository(
                db
            ).upsert_many(
                events
            )

    print()
    print(
        f"Session: "
        f"{context.session.session_name}"
    )
    print(
        f"Session key: "
        f"{context.session.session_key}"
    )

    print()
    print("Raw data")
    print(
        f"  Drivers:      {len(bundle.drivers)}"
    )
    print(
        f"  Laps:         {len(bundle.laps)}"
    )
    print(
        f"  Positions:    {len(bundle.positions)}"
    )
    print(
        f"  Intervals:    {len(bundle.intervals)}"
    )
    print(
        f"  Stints:       {len(bundle.stints)}"
    )
    print(
        f"  Pit stops:    {len(bundle.pits)}"
    )
    print(
        f"  Race control: "
        f"{len(bundle.race_control)}"
    )
    print(
        f"  Weather:      {len(bundle.weather)}"
    )

    print()
    print("High-frequency probe")
    print(
        f"  Car data:     "
        f"{len(bundle.car_data_sample)}"
    )
    print(
        f"  Location:     "
        f"{len(bundle.location_sample)}"
    )

    print()
    print(
        f"Normalized events: {len(events)}"
    )

    print(
        f"Processed file: {processed_path}"
    )

    print()
    print("Database ingestion complete.")


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--year",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--country",
        required=True,
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
    )

    args = parser.parse_args()

    asyncio.run(
        run(
            year=args.year,
            country=args.country,
            refresh=args.refresh,
        )
    )


if __name__ == "__main__":
    main()