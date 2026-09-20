import {
    useRaceStore,
} from "../stores/raceStore"


function formatNumber(
    value:
        | number
        | null
        | undefined,
    digits = 0
    ) {
    if (value == null) {
        return "—"
    }

    return value.toFixed(
        digits
    )
}


export function DriverTelemetry() {
    const selectedDriver =
        useRaceStore(
        (store) =>
            store.selectedDriver
        )

    const telemetry =
        useRaceStore(
        (store) =>
            store.telemetry
        )


    const driver =
        telemetry?.drivers.find(
        (item) =>
            item.driver ===
            selectedDriver
        )


    const car =
        driver?.car

    const position =
        driver?.position


    return (
        <section className="panel telemetry-panel">
        <div className="panel-title telemetry-title">
            <span>
            Driver Telemetry
            </span>

            <strong>
            {selectedDriver}
            </strong>
        </div>


        {!driver ? (
            <div className="empty-state">
            Waiting for telemetry...
            </div>
        ) : (
            <div className="telemetry-grid">
            <div className="telemetry-stat">
                <span>
                SPEED
                </span>

                <strong>
                {formatNumber(
                    car?.Speed
                )}
                </strong>

                <small>
                km/h
                </small>
            </div>


            <div className="telemetry-stat">
                <span>
                RPM
                </span>

                <strong>
                {formatNumber(
                    car?.RPM
                )}
                </strong>
            </div>


            <div className="telemetry-stat">
                <span>
                GEAR
                </span>

                <strong>
                {formatNumber(
                    car?.nGear
                )}
                </strong>
            </div>


            <div className="telemetry-stat">
                <span>
                THROTTLE
                </span>

                <strong>
                {formatNumber(
                    car?.Throttle
                )}
                </strong>

                <small>
                %
                </small>
            </div>


            <div className="telemetry-stat">
                <span>
                BRAKE
                </span>

                <strong>
                {car?.Brake == null
                    ? "—"
                    : car.Brake
                    ? "ON"
                    : "OFF"}
                </strong>
            </div>


            <div className="telemetry-stat">
                <span>
                DRS
                </span>

                <strong>
                {formatNumber(
                    car?.DRS
                )}
                </strong>
            </div>


            <div className="telemetry-stat">
                <span>
                CURRENT LAP
                </span>

                <strong>
                {formatNumber(
                    car?.LapNumber
                )}
                </strong>
            </div>


            <div className="telemetry-stat">
                <span>
                POSITION FEED
                </span>

                <strong>
                {position?.Status ??
                    "—"}
                </strong>
            </div>
            </div>
        )}
        </section>
    )
    }