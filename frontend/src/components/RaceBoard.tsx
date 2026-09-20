import {
    useRaceStore,
} from "../stores/raceStore"


function normaliseColour(
    colour:
        | string
        | null
        | undefined
): string {
    if (!colour) {
        return "#71717A"
    }

    return colour.startsWith("#")
        ? colour
        : `#${colour}`
}


export function RaceBoard() {
    const state =
        useRaceStore(
        (store) =>
            store.state
        )

    const selectedDriver =
        useRaceStore(
        (store) =>
            store.selectedDriver
        )

    const setSelectedDriver =
        useRaceStore(
        (store) =>
            store.setSelectedDriver
        )


    if (!state) {
        return (
        <section className="panel">
            <div className="panel-title">
            Race Order
            </div>

            <div className="empty-state">
            Waiting for race data...
            </div>
        </section>
        )
    }


    const drivers =
        Object.values(
        state.drivers
        ).sort(
        (a, b) =>
            (
            a.position ??
            999
            ) -
            (
            b.position ??
            999
            )
        )


    return (
        <section className="panel race-board">
        <div className="panel-title">
            Race Order
        </div>


        <div className="driver-list">
            {drivers.map(
            (driver) => {
                const acronym =
                driver.name_acronym ??
                driver.full_name ??
                `#${driver.driver_number}`


                const selected =
                acronym ===
                selectedDriver


                const colour =
                normaliseColour(
                    driver.team_colour
                )


                return (
                <button
                    type="button"
                    className={
                    selected
                        ? "driver-row selected-driver-row"
                        : "driver-row"
                    }
                    key={
                    driver.driver_number
                    }
                    onClick={() =>
                    setSelectedDriver(
                        acronym
                    )
                    }
                >
                    <span
                    className="team-colour-strip"
                    style={{
                        backgroundColor:
                        colour,
                    }}
                    />


                    <div className="driver-position">
                    {driver.position
                        ? `P${driver.position}`
                        : "—"}
                    </div>


                    <div className="driver-name">
                    {acronym}
                    </div>


                    <div className="driver-tyre">
                    {driver.compound ??
                        "—"}
                    </div>


                    <div className="driver-age">
                    {driver.tyre_age !=
                    null
                        ? `${driver.tyre_age}L`
                        : "—"}
                    </div>


                    <div className="driver-gap">
                    {driver.gap_to_leader ??
                        "—"}
                    </div>
                </button>
                )
            }
            )}
        </div>
        </section>
    )
    }