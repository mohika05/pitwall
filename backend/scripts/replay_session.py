import argparse
import asyncio

from app.core.config import settings
from app.domain.race_state import (
    apply_official_classification,
)
from app.persistence.database import (
    AsyncSessionLocal,
)
from app.persistence.repositories.event_repository import (
    EventRepository,
)
from app.persistence.repositories.session_repository import (
    SessionRepository,
)
from app.replay.engine import (
    ReplayEngine,
    state_fingerprint,
)


async def run(
    session_key: int,
) -> None:
    async with AsyncSessionLocal() as db:
        context = await SessionRepository(
            db
        ).get_replay_context(
            session_key
        )

        official_result = (
            await SessionRepository(
                db
            ).get_official_result(
                session_key
            )
        )

        events = await EventRepository(
            db
        ).get_for_session(
            session_key
        )

    print(
        f"Loaded {len(events)} events."
    )

    # ---------------------------------------------------------
    # FIRST REPLAY
    # ---------------------------------------------------------

    first_engine = ReplayEngine(
        context,
        events,
    )

    first_final = (
        first_engine.run_to_end()
    )

    first_hash = state_fingerprint(
        first_final
    )

    # ---------------------------------------------------------
    # SECOND REPLAY
    # ---------------------------------------------------------

    second_engine = ReplayEngine(
        context,
        events,
    )

    second_final = (
        second_engine.run_to_end()
    )

    second_hash = state_fingerprint(
        second_final
    )

    # ---------------------------------------------------------
    # DETERMINISM CHECK
    # ---------------------------------------------------------

    if first_hash != second_hash:
        raise RuntimeError(
            "Replay is not deterministic"
        )

    print(
        "Deterministic replay: PASS"
    )

    print(
        f"State fingerprint: {first_hash}"
    )

    # ---------------------------------------------------------
    # APPLY OFFICIAL POST-RACE CLASSIFICATION
    # ---------------------------------------------------------

    classified_state = (
        apply_official_classification(
            first_final,
            official_result,
        )
    )

    drivers = sorted(
        classified_state.drivers.values(),
        key=lambda driver: (
            driver.classified_position
            if driver.classified_position
            is not None
            else (
                driver.position
                if driver.position
                is not None
                else 999
            )
        ),
    )

    print()
    print(
        "Reconstructed final state "
        f"at lap "
        f"{classified_state.current_lap}"
    )

    for driver in drivers:
        print(
            f"track=P"
            f"{driver.position or '-':>2} "
            f"classified=P"
            f"{driver.classified_position or '-':>2} "
            f"{driver.name_acronym or driver.driver_number:<4} "
            f"lap={driver.current_lap:<3} "
            f"tyre={driver.compound or '-':<8} "
            f"age={driver.tyre_age}"
        )

    # ---------------------------------------------------------
    # OFFICIAL POSITION LOOKUP
    # ---------------------------------------------------------

    official_positions = {
        int(
            row["driver_number"]
        ): int(
            row["position"]
        )
        for row in official_result
        if (
            row.get(
                "driver_number"
            )
            is not None
            and row.get(
                "position"
            )
            is not None
        )
    }

    # ---------------------------------------------------------
    # TRACK POSITION VS OFFICIAL CLASSIFICATION
    # ---------------------------------------------------------

    comparable = 0
    matches = 0

    for driver in drivers:
        expected = (
            official_positions.get(
                driver.driver_number
            )
        )

        if (
            expected is None
            or driver.position is None
        ):
            continue

        comparable += 1

        if (
            expected
            == driver.position
        ):
            matches += 1

    print()
    print(
        "Track-position vs official classification: "
        f"{matches}/{comparable} match"
    )

    # ---------------------------------------------------------
    # OFFICIAL CLASSIFICATION OVERLAY VALIDATION
    # ---------------------------------------------------------

    classification_comparable = 0
    classification_matches = 0

    for driver in drivers:
        expected = (
            official_positions.get(
                driver.driver_number
            )
        )

        if (
            expected is None
            or driver.classified_position
            is None
        ):
            continue

        classification_comparable += 1

        if (
            expected
            == driver.classified_position
        ):
            classification_matches += 1

    print(
        "Official classification overlay: "
        f"{classification_matches}/"
        f"{classification_comparable} match"
    )

    # ---------------------------------------------------------
    # SAVE FINAL STATE
    # ---------------------------------------------------------

    output_dir = (
        settings.data_dir
        / "snapshots"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_dir
        / f"{session_key}_final_state.json"
    )

    output_path.write_text(
        classified_state.model_dump_json(
            indent=2
        )
    )

    print(
        f"Final state written to "
        f"{output_path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--session-key",
        required=True,
        type=int,
    )

    args = parser.parse_args()

    asyncio.run(
        run(
            args.session_key
        )
    )

if __name__ == "__main__":
    main()