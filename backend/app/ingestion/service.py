import gzip
import re
from pathlib import Path

from app.core.config import settings
from app.domain.entities import ReplayContext
from app.domain.events import (
    RaceEvent,
    sort_events,
)
from app.ingestion.normalizers.context import (
    normalize_context,
)
from app.ingestion.normalizers.intervals import (
    normalize_intervals,
)
from app.ingestion.normalizers.laps import (
    normalize_laps,
)
from app.ingestion.normalizers.pits import (
    normalize_pits,
)
from app.ingestion.normalizers.positions import (
    normalize_positions,
)
from app.ingestion.normalizers.race_control import (
    normalize_race_control,
)
from app.ingestion.normalizers.stints import (
    normalize_stints,
)
from app.ingestion.normalizers.weather import (
    normalize_weather,
)
from app.ingestion.providers.base import (
    RaceDataProvider,
    SessionDataBundle,
)
from app.storage.object_store import object_store, processed_events_key


def _slug(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        value.lower(),
    ).strip("_")

class IngestionService:
    def __init__(
        self,
        provider: RaceDataProvider,
    ) -> None:
        self.provider = provider

    def _cache_path(
        self,
        year: int,
        country_name: str,
    ) -> Path:
        path = (
            settings.data_dir
            / "raw"
            / f"{year}_{_slug(country_name)}_race.json"
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        return path

    async def get_bundle(
        self,
        year: int,
        country_name: str,
        refresh: bool = False,
    ) -> SessionDataBundle:
        cache_path = self._cache_path(
            year,
            country_name,
        )

        if (
            cache_path.exists()
            and not refresh
        ):
            return SessionDataBundle.model_validate_json(
                cache_path.read_text()
            )

        session = await self.provider.find_race_session(
            year,
            country_name,
        )

        bundle = await self.provider.fetch_bundle(
            session
        )

        cache_path.write_text(
            bundle.model_dump_json(
                indent=2
            )
        )

        return bundle

    def normalize(
        self,
        bundle: SessionDataBundle,
    ) -> tuple[
        ReplayContext,
        list[RaceEvent],
    ]:
        context = normalize_context(
            bundle
        )

        events: list[RaceEvent] = []

        events.extend(
            normalize_stints(
                bundle.stints,
                bundle.laps,
                context.session.date_start,
            )
        )

        events.extend(
            normalize_positions(
                bundle.positions
            )
        )

        events.extend(
            normalize_intervals(
                bundle.intervals
            )
        )

        events.extend(
            normalize_pits(
                bundle.pits
            )
        )

        events.extend(
            normalize_laps(
                bundle.laps
            )
        )

        events.extend(
            normalize_race_control(
                bundle.race_control
            )
        )

        events.extend(
            normalize_weather(
                bundle.weather
            )
        )

        return (
            context,
            sort_events(events),
        )

    async def save_processed_events(
        self,
        session_key: int,
        events: list[RaceEvent],
    ) -> dict:
        key = processed_events_key(session_key)
        path = object_store.local_path(key)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = "[" + ",".join(
            event.model_dump_json()
            for event in events
        ) + "]"

        with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as destination:
            destination.write(payload)

        return await object_store.publish(path, key)
