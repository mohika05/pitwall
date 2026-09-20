import {
    useRaceStore,
} from "../stores/raceStore"


function displayNumber(
    value:
        | number
        | null
        | undefined,
    suffix = "",
    digits = 1
    ) {
    if (value == null) {
        return "—"
    }

    return (
        `${value.toFixed(digits)}` +
        suffix
    )
}


export function RaceInfo() {
    const state =
        useRaceStore(
        (store) =>
            store.state
        )


    if (!state) {
        return null
    }


    const weather =
        state.weather


    return (
        <div className="race-info-grid">

        {/* ==========================================
            RACE CONTROL
            ========================================== */}

        <section className="panel race-control-panel">
            <div className="panel-title">
            Race Control
            </div>

            <div className="race-control-content">
            {state.latest_race_control_message ? (
                <p>
                {
                    state.latest_race_control_message
                }
                </p>
            ) : (
                <p className="muted">
                No race-control message yet.
                </p>
            )}
            </div>
        </section>


        {/* ==========================================
            WEATHER
            ========================================== */}

        <section className="panel weather-panel">
            <div className="panel-title">
            Weather
            </div>


            <div className="weather-grid">

            <div className="weather-stat">
                <span>
                AIR
                </span>

                <strong>
                {displayNumber(
                    weather?.air_temperature,
                    "°C"
                )}
                </strong>
            </div>


            <div className="weather-stat">
                <span>
                TRACK
                </span>

                <strong>
                {displayNumber(
                    weather?.track_temperature,
                    "°C"
                )}
                </strong>
            </div>


            <div className="weather-stat">
                <span>
                HUMIDITY
                </span>

                <strong>
                {displayNumber(
                    weather?.humidity,
                    "%"
                )}
                </strong>
            </div>


            <div className="weather-stat">
                <span>
                RAIN
                </span>

                <strong>
                {
                    weather?.rainfall == null
                    ? "—"
                    : weather.rainfall > 0
                        ? "YES"
                        : "NO"
                }
                </strong>
            </div>


            <div className="weather-stat">
                <span>
                WIND
                </span>

                <strong>
                {displayNumber(
                    weather?.wind_speed,
                    " km/h"
                )}
                </strong>
            </div>


            <div className="weather-stat">
                <span>
                PRESSURE
                </span>

                <strong>
                {displayNumber(
                    weather?.pressure,
                    " mbar",
                    0
                )}
                </strong>
            </div>

            </div>
        </section>

        </div>
    )
    }