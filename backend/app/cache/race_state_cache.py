from app.cache.redis import (
    redis_client,
)
from app.domain.race_state import (
    RaceState,
)


class RaceStateCache:
    PREFIX = "pitwall:race"

    def __init__(self, namespace: str | None = None):
        self.namespace = namespace

    @classmethod
    def _key(
        cls,
        session_key: int,
    ) -> str:
        return (
            f"{cls.PREFIX}:"
            f"{session_key}:state"
        )

    async def set(
        self,
        state: RaceState,
        ttl_seconds: int = 3600,
    ) -> None:
        await redis_client.set(
            f"{self.PREFIX}:{self.namespace}:state" if self.namespace else self._key(state.session_key),
            state.model_dump_json(),
            ex=ttl_seconds,
        )

    async def get(
        self,
        session_key: int,
    ) -> RaceState | None:
        payload = await redis_client.get(
            self._key(
                session_key
            )
        )

        if payload is None:
            return None

        return RaceState.model_validate_json(
            payload
        )

    async def delete(
        self,
        session_key: int,
    ) -> None:
        await redis_client.delete(
            self._key(
                session_key
            )
        )